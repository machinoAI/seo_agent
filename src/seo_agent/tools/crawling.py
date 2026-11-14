"""T02 `discover_site_urls`, T03 `crawl_website`, T04 page extraction.

Network code is thin; the parsing helpers (`normalize_url`, `parse_html`,
`parse_sitemap`, `parse_robots`) are pure functions with unit tests.
"""

import asyncio
import gzip
import io
import json
import re
import zlib
from collections import Counter
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
from lxml import etree

from seo_agent.config import get_settings
from seo_agent.tools.base import ToolOutput, ToolRequest, recorded_tool
from seo_agent.tools.http import FetchError, SafeHttpClient

ASSET_EXTENSIONS = frozenset(
    ".jpg .jpeg .png .gif .webp .avif .svg .ico .bmp .tif .tiff .mp4 .webm .mov .avi .mp3 .wav "
    ".ogg .pdf .zip .gz .rar .7z .tar .dmg .exe .msi .css .js .json .xml .txt .woff .woff2 .ttf "
    ".eot .otf .csv .xls .xlsx .doc .docx .ppt .pptx".split()
)
_TRACKING_PARAMS = re.compile(r"^(utm_\w+|gclid|fbclid|msclkid|mc_cid|mc_eid|_ga)$", re.I)
_WORD = re.compile(r"\w+", re.UNICODE)
MAX_LINKS_PER_PAGE = 300
MAX_SITEMAP_BYTES = 50_000_000
MAX_ROBOTS_BYTES = 500_000


# ── Pure helpers ─────────────────────────────────────────────────────────────


def normalize_url(url: str, base: str | None = None) -> str | None:
    """Absolute http(s) URL without fragment, default port or tracking parameters."""
    try:
        parts = urlsplit(urljoin(base, url.strip()) if base else url.strip())
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower().rstrip(".")
    default_port = 443 if scheme == "https" else 80
    netloc = host if port in (None, default_port) else f"{host}:{port}"
    query = urlencode(
        [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
         if not _TRACKING_PARAMS.match(k)]
    )
    return urlunsplit((scheme, netloc, parts.path or "/", query, ""))


def is_asset(url: str) -> bool:
    path = urlsplit(url).path.lower()
    return any(path.endswith(ext) for ext in ASSET_EXTENSIONS)


def template_of(url: str) -> str:
    """Group URLs by section and depth: /jobs, /jobs/*, /jobs/*/* … (one page template each)."""
    segments = [s for s in urlsplit(url).path.split("/") if s]
    if not segments:
        return "/"
    return "/" + "/".join([segments[0], *["*"] * min(len(segments) - 1, 2)])


def stratified_sample(urls: list[str], size: int) -> list[str]:
    """Pick `size` URLs spread across templates (round-robin), so a small crawl still
    covers hubs and detail pages of every section instead of the first sitemap entries."""
    groups: dict[str, list[str]] = {}
    for url in urls:
        groups.setdefault(template_of(url), []).append(url)
    queues = [iter(group) for group in groups.values()]
    sample: list[str] = []
    while queues and len(sample) < size:
        for queue in list(queues):
            url = next(queue, None)
            if url is None:
                queues.remove(queue)
                continue
            sample.append(url)
            if len(sample) >= size:
                break
    return sample


def parse_robots(text: str) -> RobotFileParser:
    parser = RobotFileParser()
    parser.parse(text.splitlines())
    return parser


def parse_sitemap(content: bytes) -> tuple[list[str], list[str]]:
    """Return (page URLs, child sitemap URLs) from a sitemap or sitemap index."""
    if content[:2] == b"\x1f\x8b":  # gzip
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(content)) as gz:
                content = gz.read(MAX_SITEMAP_BYTES)
        except (OSError, EOFError, zlib.error):  # truncated or corrupt archive
            return [], []
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=True)
    try:
        root = etree.fromstring(content, parser)
    except etree.XMLSyntaxError:
        return [], []
    if root is None:
        return [], []
    locs = [
        el.text.strip()
        for el in root.iter()
        if isinstance(el.tag, str) and etree.QName(el).localname == "loc" and el.text
    ]
    if etree.QName(root).localname == "sitemapindex":
        return [], locs
    return locs, []


def _structured_data_types(soup: BeautifulSoup) -> list[str]:
    types: set[str] = set()

    def collect(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                collect(item)
        elif isinstance(node, dict):
            value = node.get("@type")
            for t in value if isinstance(value, list) else [value]:
                if isinstance(t, str):
                    types.add(t)
            if "@graph" in node:
                collect(node["@graph"])

    for script in soup.find_all("script", type=re.compile(r"application/ld\+json", re.I)):
        try:
            collect(json.loads(script.string or ""))
        except ValueError:
            types.add("invalid-json-ld")
    for element in soup.find_all(attrs={"itemtype": True}):
        types.add(str(element["itemtype"]).rstrip("/").rsplit("/", 1)[-1])
    return sorted(types)


def parse_html(url: str, html: str, allowed_hosts: set[str]) -> dict[str, Any]:
    """Extract SEO-relevant metadata and links from an HTML page."""
    soup = BeautifulSoup(html, "lxml")

    def meta(name: str) -> str | None:
        tag = soup.find("meta", attrs={"name": re.compile(f"^{name}$", re.I)})
        content = tag.get("content") if tag else None
        return str(content).strip() if content is not None else None

    base_tag = soup.find("base", href=True)
    base_url = urljoin(url, str(base_tag["href"])) if base_tag else url

    canonical = None
    hreflang_count = 0
    for link in soup.find_all("link", href=True):
        rels = [r.lower() for r in link.get("rel", [])]
        if "canonical" in rels and canonical is None:
            canonical = normalize_url(str(link["href"]), base_url)
        if "alternate" in rels and link.get("hreflang"):
            hreflang_count += 1

    internal: list[str] = []
    external_count = 0
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue
        target = normalize_url(href, base_url)
        if target is None:
            continue
        if urlsplit(target).hostname in allowed_hosts:
            if target not in internal and len(internal) < MAX_LINKS_PER_PAGE:
                internal.append(target)
        else:
            external_count += 1

    structured_data = _structured_data_types(soup)
    images = soup.find_all("img")
    title = soup.title.get_text(" ", strip=True) if soup.title else None
    html_tag = soup.find("html")
    h1 = [h.get_text(" ", strip=True) for h in soup.find_all("h1")]
    h2 = [h.get_text(" ", strip=True) for h in soup.find_all("h2")]
    description = meta("description")

    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    words = len(_WORD.findall(soup.get_text(" ", strip=True)))

    return {
        "parsed": True,
        "title": title or None,
        "title_length": len(title) if title else 0,
        "meta_description": description or None,
        "description_length": len(description) if description else 0,
        "meta_robots": (meta("robots") or "").lower() or None,
        "canonical": canonical,
        "lang": (html_tag.get("lang") if html_tag else None) or None,
        "h1": h1[:5],
        "h1_count": len(h1),
        "h2": h2[:10],
        "h2_count": len(h2),
        "word_count": words,
        "structured_data_types": structured_data,
        "hreflang_count": hreflang_count,
        "images": len(images),
        "images_missing_alt": sum(1 for img in images if img.get("alt") is None),
        "internal_links": internal,
        "external_link_count": external_count,
    }


# ── Tools ────────────────────────────────────────────────────────────────────


class DiscoverRequest(ToolRequest):
    start_url: str
    allowed_hosts: list[str]
    max_urls: int = 50_000
    max_sitemaps: int = 50


@recorded_tool("discover_site_urls")
async def discover_site_urls(request: DiscoverRequest) -> ToolOutput:
    """Read robots.txt and sitemaps (incl. sitemap indexes) and list in-scope URLs."""
    settings = get_settings()
    allowed = set(request.allowed_hosts)
    start = urlsplit(request.start_url)
    origin = f"{start.scheme}://{start.netloc}"
    warnings: list[str] = []

    robots: dict[str, Any] = {"url": f"{origin}/robots.txt", "status_code": None, "found": False}
    robots_txt = ""
    sitemaps: list[dict[str, Any]] = []
    urls: list[str] = []

    async with SafeHttpClient.from_settings(settings, allowed_hosts=allowed) as client:
        try:
            response = await client.fetch(robots["url"], max_bytes=MAX_ROBOTS_BYTES)
            robots["status_code"] = response.status_code
            if response.status_code == 200:
                robots["found"] = True
                robots_txt = response.text()
        except FetchError as exc:
            robots["error"] = exc.code

        parser = parse_robots(robots_txt) if robots["found"] else None
        declared = list(parser.site_maps() or []) if parser else []
        robots["declared_sitemaps"] = declared
        queue = declared or [f"{origin}/sitemap.xml"]
        seen: set[str] = set()

        while queue and len(seen) < request.max_sitemaps and len(urls) < request.max_urls:
            sitemap_url = queue.pop(0)
            if sitemap_url in seen:
                continue
            seen.add(sitemap_url)
            report: dict[str, Any] = {"url": sitemap_url}
            sitemaps.append(report)
            try:
                response = await client.fetch(sitemap_url, max_bytes=MAX_SITEMAP_BYTES)
            except FetchError as exc:
                report["error"] = exc.code
                continue
            report["status_code"] = response.status_code
            if response.status_code != 200:
                continue
            page_urls, children = parse_sitemap(response.body)
            in_scope = [
                u for u in (normalize_url(x) for x in page_urls)
                if u and urlsplit(u).hostname in allowed and not is_asset(u)
            ]
            urls.extend(in_scope)
            queue.extend(children)
            report.update(
                urls=len(page_urls), in_scope=len(in_scope), child_sitemaps=len(children)
            )

    urls = list(dict.fromkeys(urls))[: request.max_urls]
    blocked = parser is not None and not parser.can_fetch(
        settings.crawler_user_agent, request.start_url
    )
    if not robots["found"]:
        warnings.append("robots.txt not found or not readable.")
    if not urls:
        warnings.append("No URLs found in sitemaps.")
    if blocked:
        warnings.append("robots.txt disallows crawling the start URL for this user agent.")

    templates = Counter(template_of(u) for u in urls)
    return ToolOutput(
        source="robots.txt+sitemaps",
        data={
            "robots": robots,
            "robots_txt": robots_txt[:20_000],
            "sitemaps": sitemaps,
            "urls": urls,
            "url_count": len(urls),
            "url_count_by_template": dict(templates.most_common(50)),
            "start_url_blocked_by_robots": blocked,
        },
        warnings=warnings,
    )


class CrawlRequest(ToolRequest):
    start_url: str
    allowed_hosts: list[str]
    seed_urls: list[str] = []
    robots_txt: str = ""
    max_pages: int = 500
    max_depth: int = 5


@recorded_tool("crawl_website")
async def crawl_website(request: CrawlRequest) -> ToolOutput:
    """Breadth-first crawl inside the site, respecting robots.txt and the page budget."""
    settings = get_settings()
    allowed = set(request.allowed_hosts)
    robots = parse_robots(request.robots_txt) if request.robots_txt else None
    user_agent = settings.crawler_user_agent

    queue: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
    seen: set[str] = set()
    pages: list[dict[str, Any]] = []
    blocked_by_robots: list[str] = []

    def enqueue(url: str | None, depth: int) -> None:
        if url is None or url in seen or len(seen) >= request.max_pages or is_asset(url):
            return
        if urlsplit(url).hostname not in allowed:
            return
        seen.add(url)
        queue.put_nowait((url, depth))

    enqueue(normalize_url(request.start_url), 0)
    for seed in request.seed_urls:
        enqueue(normalize_url(seed), 1)

    async with SafeHttpClient.from_settings(settings, allowed_hosts=allowed) as client:

        async def worker() -> None:
            while True:
                url, depth = await queue.get()
                try:
                    if robots is not None and not robots.can_fetch(user_agent, url):
                        blocked_by_robots.append(url)
                        continue
                    try:
                        page = await _crawl_page(client, url, depth, allowed)
                    except Exception:  # one bad page must not stop the crawl
                        page = {"url": url, "depth": depth, "status_code": None,
                                "error": "unexpected_error"}
                    pages.append(page)
                    final = page.get("final_url")
                    if isinstance(final, str):
                        seen.add(final)
                    if depth < request.max_depth:
                        for link in page.get("internal_links", []):
                            enqueue(link, depth + 1)
                    await asyncio.sleep(settings.crawler_delay_seconds)
                finally:
                    queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(settings.crawler_concurrency)]
        try:
            await queue.join()
        finally:
            for task in workers:
                task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

    html_pages = [p for p in pages if p.get("parsed")]
    status_counts: dict[str, int] = {}
    for page in pages:
        key = str(page.get("status_code") or page.get("error") or "unknown")
        status_counts[key] = status_counts.get(key, 0) + 1
    warnings = []
    if len(seen) >= request.max_pages:
        warnings.append(f"Page budget of {request.max_pages} reached; the crawl is a sample.")
    if not html_pages:
        warnings.append("No HTML pages could be crawled.")

    return ToolOutput(
        source="crawler",
        data={
            "start_url": request.start_url,
            "pages": pages,
            "blocked_by_robots": blocked_by_robots,
            "stats": {
                "pages_fetched": len(pages),
                "html_pages": len(html_pages),
                "blocked_by_robots": len(blocked_by_robots),
                "status_counts": status_counts,
                "budget_reached": len(seen) >= request.max_pages,
            },
        },
        warnings=warnings,
    )


async def _crawl_page(
    client: SafeHttpClient, url: str, depth: int, allowed: set[str]
) -> dict[str, Any]:
    try:
        response = await client.fetch(url)
    except FetchError as exc:
        return {"url": url, "depth": depth, "status_code": None, "error": exc.code}
    page: dict[str, Any] = {
        "url": url,
        "final_url": normalize_url(response.final_url) or response.final_url,
        "depth": depth,
        "status_code": response.status_code,
        "redirects": response.redirects,
        "content_type": response.content_type,
        "elapsed_ms": response.elapsed_ms,
        "bytes": len(response.body),
        "truncated": response.truncated,
        "x_robots_tag": response.headers.get("x-robots-tag"),
    }
    if response.status_code == 200 and response.is_html:
        page.update(parse_html(response.final_url, response.text(), allowed))
    return page
