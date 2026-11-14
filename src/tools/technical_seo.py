"""T05/T06/T07 `analyze_technical_seo`: deterministic checks over the crawl results.

Rules are plain Python so findings are reproducible and testable; the SEO Audit Agent
(LLM) then prioritizes and explains them. Every finding lists the affected URLs with
the measured value for each (e.g. response time, title length), so it can be acted on
page by page. Also returns per-template health, structured data by template and which
search / AI crawlers robots.txt allows.
"""

import statistics
from collections import Counter, defaultdict
from typing import Any
from urllib.parse import urlsplit

from src.persistence.output_store import read_recorded
from src.tools.base import ToolOutput, ToolRequest, recorded_tool
from src.tools.crawling import parse_robots, template_of

RULES_VERSION = "tech-rules-v2"
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
MAX_EXAMPLES = 10
MAX_AFFECTED = 500

TITLE_MAX, TITLE_MIN = 60, 15
DESCRIPTION_MAX = 160
THIN_CONTENT_WORDS = 200
SLOW_RESPONSE_MS = 1500

# Crawlers that decide whether pages can appear in search results / AI answers.
SEARCH_CRAWLERS = {
    "Googlebot": "Google Search",
    "Bingbot": "Bing (also feeds Copilot)",
    "OAI-SearchBot": "ChatGPT search",
    "ChatGPT-User": "ChatGPT browsing on user request",
    "PerplexityBot": "Perplexity answers",
    "Claude-SearchBot": "Claude search",
}
# Crawlers that collect training data: blocking them is a business choice, not an error.
TRAINING_CRAWLERS = {
    "GPTBot": "OpenAI training",
    "Google-Extended": "Gemini training",
    "ClaudeBot": "Anthropic training",
    "Applebot-Extended": "Apple Intelligence training",
    "CCBot": "Common Crawl",
}

Item = tuple[str, Any]  # (url, measured value)


def _finding(
    issue_type: str,
    severity: str,
    items: list[Item],
    evidence: str,
    source_tool: str,
    observed_at: str | None,
) -> dict[str, Any]:
    return {
        "issue_type": issue_type,
        "severity": severity,
        "affected_count": len(items),
        "example_urls": [url for url, _ in items[:MAX_EXAMPLES]],
        "affected": [{"url": url, "value": value} for url, value in items[:MAX_AFFECTED]],
        "evidence": evidence,
        "source_tool": source_tool,
        "observed_at": observed_at,
    }


def _duplicates(pages: list[dict[str, Any]], field: str) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for page in pages:
        value = page.get(field)
        if value:
            groups[value.strip().lower()].append(page["url"])
    return {k: v for k, v in groups.items() if len(v) > 1}


# ── Site-level analyses (also used as evidence) ─────────────────────────────


def crawler_access(robots_txt: str, home_url: str) -> dict[str, Any]:
    """Which search / AI crawlers robots.txt lets fetch the homepage."""
    if not robots_txt:
        return {"robots_txt": "missing", "search": {}, "training": {}}
    robots = parse_robots(robots_txt)

    def check(bots: dict[str, str]) -> dict[str, str]:
        return {
            f"{bot} ({purpose})": "allowed" if robots.can_fetch(bot, home_url) else "blocked"
            for bot, purpose in bots.items()
        }

    return {"search": check(SEARCH_CRAWLERS), "training": check(TRAINING_CRAWLERS)}


def section_health(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per URL template (e.g. /jobs/*/*): size, errors, speed, content and schema."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for page in pages:
        groups[template_of(page["url"])].append(page)
    rows = []
    for template, group in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        html = [p for p in group if p.get("parsed")]
        times = [p["elapsed_ms"] for p in group if p.get("elapsed_ms")]
        words = [p.get("word_count", 0) for p in html]
        schema: Counter[str] = Counter(t for p in html for t in p.get("structured_data_types", []))
        rows.append({
            "template": template,
            "pages": len(group),
            "errors": sum(1 for p in group if (p.get("status_code") or 0) >= 400
                          or p.get("error")),
            "median_response_ms": round(statistics.median(times)) if times else None,
            "max_response_ms": max(times) if times else None,
            "median_words": round(statistics.median(words)) if words else None,
            "missing_h1": sum(1 for p in html if p.get("h1_count", 0) == 0),
            "missing_description": sum(1 for p in html if not p.get("meta_description")),
            "structured_data": [t for t, _ in schema.most_common(8)],
            "example_url": group[0]["url"],
        })
    return rows


# ── Rules ────────────────────────────────────────────────────────────────────


def find_issues(
    crawl: dict[str, Any],
    discovery: dict[str, Any] | None = None,
    validation: dict[str, Any] | None = None,
    *,
    crawled_at: str | None = None,
    discovered_at: str | None = None,
    validated_at: str | None = None,
) -> list[dict[str, Any]]:
    """Apply the rule set; return findings (most severe first) with per-URL values."""
    pages: list[dict[str, Any]] = crawl.get("pages", [])
    start_url = crawl.get("start_url", "")
    html = [p for p in pages if p.get("parsed")]
    home = {start_url, start_url.rstrip("/") + "/"}
    findings: list[dict[str, Any]] = []
    sources = {
        "crawl": ("crawl_website", crawled_at),
        "discovery": ("discover_site_urls", discovered_at),
        "validation": ("validate_domain", validated_at),
    }

    def add(issue: str, severity: str, items: list[Item], evidence: str,
            tool: str = "crawl") -> None:
        if items:
            findings.append(_finding(issue, severity, items, evidence, *sources[tool]))

    def per_page(selected: list[dict[str, Any]], field: str) -> list[Item]:
        return [(p["url"], p.get(field)) for p in selected]

    # ── Homepage and site level ─────────────────────────────────────────────
    if validation:
        hops = validation.get("redirects") or []
        final = validation.get("final_url", "")
        home_url = validation.get("home_url", "")
        if hops and urlsplit(final).path not in ("", "/"):
            add("homepage_redirects_to_inner_page", "medium", [(home_url, " -> ".join(hops))],
                f"The homepage has no content of its own: it redirects to {final} "
                f"in {len(hops)} hop(s). Serve a real homepage or use a single 301.",
                "validation")
        elif len(hops) >= 2:
            add("homepage_redirect_chain", "low", [(home_url, " -> ".join(hops))],
                f"The homepage passes through {len(hops)} redirects.", "validation")
    if discovery is not None:
        robots = discovery.get("robots", {})
        if discovery.get("start_url_blocked_by_robots"):
            add("robots_blocks_site", "critical", [(start_url, "disallowed")],
                "robots.txt disallows the homepage for crawlers.", "discovery")
        if not robots.get("found"):
            add("robots_txt_missing", "low", [(robots.get("url", ""), robots.get("status_code"))],
                "robots.txt was not found or returned an error.", "discovery")
        elif not robots.get("declared_sitemaps"):
            add("robots_missing_sitemap", "low", [(robots.get("url", ""), "no Sitemap: line")],
                "robots.txt does not declare the XML sitemap; add a 'Sitemap:' line.",
                "discovery")
        if not discovery.get("url_count"):
            checked = [(s.get("url", ""), s.get("status_code") or s.get("error"))
                       for s in discovery.get("sitemaps", [])]
            add("sitemap_missing", "medium", checked or [(start_url, None)],
                "No URLs were found in an XML sitemap.", "discovery")
        access = crawler_access(discovery.get("robots_txt", ""), start_url)
        blocked = [bot for bot, state in access.get("search", {}).items() if state == "blocked"]
        if blocked:
            add("search_crawlers_blocked", "high", [(start_url, ", ".join(blocked))],
                "robots.txt blocks crawlers that power search results or AI answers.",
                "discovery")
    if start_url.startswith("http://"):
        add("no_https", "high", [(start_url, "http")], "The site is served over plain HTTP.")

    # ── Status codes, fetch errors, redirects ───────────────────────────────
    errors = [p for p in pages if (p.get("status_code") or 0) >= 400]
    if errors:
        codes = Counter(p["status_code"] for p in errors)
        severity = "critical" if any(p["url"] in home for p in errors) else "high"
        add("http_errors", severity,
            [(p["url"], f"HTTP {p['status_code']} after {p.get('elapsed_ms')} ms") for p in errors],
            "Error responses: " + ", ".join(f"{c} x{n}" for c, n in codes.most_common()))
    failed = [p for p in pages if p.get("status_code") is None and p.get("error")]
    if failed:
        reasons = Counter(p["error"] for p in failed)
        add("fetch_failures", "medium", per_page(failed, "error"),
            "Could not fetch: " + ", ".join(f"{r} x{n}" for r, n in reasons.most_common()))
    chains = [p for p in pages if len(p.get("redirects") or []) >= 2]
    add("redirect_chains", "medium",
        [(p["url"], " -> ".join(p["redirects"])) for p in chains],
        "URLs that pass through two or more redirects before the final page.")

    # ── Internal links ──────────────────────────────────────────────────────
    status_by_url = {p["url"]: p.get("status_code") for p in pages}
    redirected = {p["url"] for p in pages if p.get("redirects")}
    broken: list[Item] = []
    to_redirect: list[Item] = []
    for page in html:
        links = page.get("internal_links", [])
        broken_here = [link for link in links if (status_by_url.get(link) or 0) >= 400]
        if broken_here:
            broken.append((page["url"], "links to " + ", ".join(broken_here[:5])))
        redirecting = [link for link in links if link in redirected]
        if redirecting:
            to_redirect.append((page["url"], "links to " + ", ".join(redirecting[:5])))
    add("broken_internal_links", "high", broken,
        "Pages linking to URLs that return 4xx/5xx; fix or remove those links.")
    add("internal_links_to_redirects", "low", to_redirect,
        "Pages linking to URLs that redirect; link to the final URL instead.")

    # ── Indexability ────────────────────────────────────────────────────────
    noindex = [
        p for p in pages
        if "noindex" in (p.get("meta_robots") or "") or "noindex" in (p.get("x_robots_tag") or "")
    ]
    add("noindex_pages", "critical" if any(p["url"] in home for p in noindex) else "high",
        [(p["url"], p.get("meta_robots") or p.get("x_robots_tag")) for p in noindex],
        "Pages excluded from indexing via meta robots or X-Robots-Tag.")
    elsewhere = [p for p in html
                 if p.get("canonical") and p["canonical"] not in (p["url"], p.get("final_url"))]
    add("canonical_points_elsewhere", "low", per_page(elsewhere, "canonical"),
        "Canonical tag names a different URL; confirm this is intended.")
    add("missing_canonical", "low", [(p["url"], None) for p in html if not p.get("canonical")],
        "No canonical tag.")
    add("blocked_by_robots", "medium",
        [(u, "disallowed") for u in crawl.get("blocked_by_robots", [])],
        "Linked URLs that robots.txt disallows; check they are meant to be hidden.")

    # ── Titles, descriptions, headings ──────────────────────────────────────
    add("missing_title", "high", [(p["url"], None) for p in html if not p.get("title")],
        "No <title>.")
    add("title_too_long", "low",
        [(p["url"], f"{p['title_length']} chars: {p['title']}") for p in html
         if p.get("title_length", 0) > TITLE_MAX],
        f"Title longer than {TITLE_MAX} characters may be truncated in results.")
    add("title_too_short", "low",
        [(p["url"], f"{p['title_length']} chars: {p['title']}") for p in html
         if 0 < p.get("title_length", 0) < TITLE_MIN],
        f"Title shorter than {TITLE_MIN} characters.")
    for value, urls in _duplicates(html, "title").items():
        add("duplicate_title", "medium", [(u, value[:80]) for u in urls],
            f"Same title on {len(urls)} pages.")
    add("missing_meta_description", "medium",
        [(p["url"], None) for p in html if not p.get("meta_description")],
        "No meta description.")
    add("description_too_long", "low",
        [(p["url"], f"{p['description_length']} chars") for p in html
         if p.get("description_length", 0) > DESCRIPTION_MAX],
        f"Meta description longer than {DESCRIPTION_MAX} characters.")
    for value, urls in _duplicates(html, "meta_description").items():
        add("duplicate_meta_description", "low", [(u, value[:80]) for u in urls],
            f"Same description on {len(urls)} pages.")
    add("missing_h1", "medium",
        [(p["url"], f"{p.get('word_count', 0)} words on page") for p in html
         if p.get("h1_count", 0) == 0],
        "No <h1>.")
    add("multiple_h1", "low",
        [(p["url"], f"{p['h1_count']} H1s: " + " | ".join(p.get("h1", [])[:3])) for p in html
         if p.get("h1_count", 0) > 1],
        "More than one <h1>.")

    # ── Content, structured data, accessibility, speed ──────────────────────
    thin = [p for p in html if p.get("word_count", 0) < THIN_CONTENT_WORDS]
    thin_severity = "medium" if html and len(thin) / len(html) > 0.3 else "low"
    add("thin_content", thin_severity,
        [(p["url"], f"{p.get('word_count', 0)} words") for p in thin],
        f"Fewer than {THIN_CONTENT_WORDS} words of text in the HTML (content loaded later "
        "by JavaScript is not counted).")
    no_schema = [p for p in html if not p.get("structured_data_types")]
    add("missing_structured_data", "medium" if any(p["url"] in home for p in no_schema) else "low",
        [(p["url"], None) for p in no_schema],
        "No JSON-LD or microdata structured data found.")
    add("invalid_structured_data", "medium",
        [(p["url"], "invalid JSON-LD") for p in html
         if "invalid-json-ld" in p.get("structured_data_types", [])],
        "JSON-LD block that is not valid JSON.")
    add("images_missing_alt", "low",
        [(p["url"], f"{p['images_missing_alt']} of {p.get('images', 0)} images") for p in html
         if p.get("images_missing_alt", 0)],
        "Images without an alt attribute.")
    add("missing_lang", "low", [(p["url"], None) for p in html if not p.get("lang")],
        "No lang attribute on <html>.")
    slow = sorted((p for p in pages if (p.get("elapsed_ms") or 0) > SLOW_RESPONSE_MS),
                  key=lambda p: -p["elapsed_ms"])
    add("slow_server_response", "medium", [(p["url"], f"{p['elapsed_ms']} ms") for p in slow],
        f"HTML took longer than {SLOW_RESPONSE_MS} ms to download (crawler timing from this "
        "machine, not real users; confirm with PageSpeed TTFB).")
    add("truncated_pages", "low", [(p["url"], f"{p.get('bytes')} bytes") for p in pages
                                   if p.get("truncated")],
        "Page larger than the response size limit; analysis used the first part only.")

    findings.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], -f["affected_count"]))
    return findings


class TechnicalAuditRequest(ToolRequest):
    crawl_path: str
    discovery_path: str | None = None
    validation_path: str | None = None


@recorded_tool("analyze_technical_seo")
def analyze_technical_seo(request: TechnicalAuditRequest) -> ToolOutput:
    def load(path: str | None) -> tuple[Any, str | None]:
        if not path:
            return None, None
        result = read_recorded(path)["result"]
        return result.get("data"), result.get("completed_at")

    crawl, crawled_at = load(request.crawl_path)
    discovery, discovered_at = load(request.discovery_path)
    validation, validated_at = load(request.validation_path)
    crawl = crawl or {}

    findings = find_issues(
        crawl, discovery, validation,
        crawled_at=crawled_at, discovered_at=discovered_at, validated_at=validated_at,
    )
    return ToolOutput(
        source=RULES_VERSION,
        data={
            "rules_version": RULES_VERSION,
            "pages_analyzed": len([p for p in crawl.get("pages", []) if p.get("parsed")]),
            "findings": findings,
            "counts_by_severity": dict(Counter(f["severity"] for f in findings)),
            "section_health": section_health(crawl.get("pages", [])),
            "crawler_access": crawler_access(
                (discovery or {}).get("robots_txt", ""), crawl.get("start_url", "")
            ),
        },
    )
