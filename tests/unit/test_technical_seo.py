from typing import Any

from src.tools.technical_seo import crawler_access, find_issues, section_health

HOME = "https://machinoai.in/"


def _page(url: str, **fields: Any) -> dict[str, Any]:
    page = {
        "url": url,
        "final_url": url,
        "status_code": 200,
        "parsed": True,
        "title": f"Title for {url}",
        "title_length": 30,
        "meta_description": f"Description for {url}",
        "description_length": 50,
        "canonical": url,
        "lang": "en",
        "h1_count": 1,
        "word_count": 600,
        "structured_data_types": ["Organization"],
        "images_missing_alt": 0,
        "internal_links": [],
        "elapsed_ms": 200,
    }
    page.update(fields)
    return page


def _issues(pages: list[dict[str, Any]], **discovery: Any) -> dict[str, dict[str, Any]]:
    crawl = {"start_url": HOME, "pages": pages, "blocked_by_robots": []}
    robots = {"found": True, "declared_sitemaps": [HOME + "sitemap.xml"]}
    disc = {"robots": robots, "url_count": 5, **discovery}
    return {f["issue_type"]: f for f in find_issues(crawl, disc)}


def test_healthy_site_has_no_issues() -> None:
    assert _issues([_page(HOME), _page(HOME + "a")]) == {}


def test_broken_links_errors_and_metadata_problems() -> None:
    pages = [
        _page(HOME, internal_links=[HOME + "gone", HOME + "old"]),
        {"url": HOME + "gone", "status_code": 404},
        {"url": HOME + "old", "status_code": 200, "redirects": [HOME + "new"]},
        _page(HOME + "x", title=None, title_length=0, h1_count=0, meta_description=None),
        _page(HOME + "y", title="Same", title_length=4),
        _page(HOME + "z", title="Same", title_length=4),
    ]
    issues = _issues(pages)

    assert issues["http_errors"]["severity"] == "high"
    assert issues["broken_internal_links"]["example_urls"] == [HOME]
    assert issues["internal_links_to_redirects"]["affected_count"] == 1
    assert issues["missing_title"]["example_urls"] == [HOME + "x"]
    assert issues["missing_h1"]["affected_count"] == 1
    assert issues["missing_meta_description"]["affected_count"] == 1
    assert issues["duplicate_title"]["affected_count"] == 2


def test_noindex_homepage_is_critical_and_sorted_first() -> None:
    crawl = {"start_url": HOME, "pages": [_page(HOME, meta_robots="noindex, nofollow")]}
    robots = {"found": True, "declared_sitemaps": [HOME + "sitemap.xml"]}
    findings = find_issues(crawl, {"robots": robots, "url_count": 1})

    assert findings[0]["issue_type"] == "noindex_pages"
    assert findings[0]["severity"] == "critical"


def test_site_level_discovery_issues() -> None:
    issues = _issues(
        [_page(HOME)], start_url_blocked_by_robots=True, robots={"found": False}, url_count=0
    )
    assert issues["robots_blocks_site"]["severity"] == "critical"
    assert "robots_txt_missing" in issues
    assert issues["sitemap_missing"]["severity"] == "medium"


def test_findings_carry_measured_value_per_url() -> None:
    issues = _issues([_page(HOME), _page(HOME + "slow", elapsed_ms=4200),
                      _page(HOME + "thin", word_count=64, h1_count=0)])

    assert issues["slow_server_response"]["affected"] == [
        {"url": HOME + "slow", "value": "4200 ms"}
    ]
    assert issues["thin_content"]["affected"][0]["value"] == "64 words"
    assert issues["missing_h1"]["affected"][0]["value"] == "64 words on page"


def test_homepage_redirect_and_robots_without_sitemap_line() -> None:
    crawl = {"start_url": HOME + "concepts", "pages": [_page(HOME + "concepts")]}
    discovery = {"robots": {"found": True, "declared_sitemaps": [], "url": HOME + "robots.txt"},
                 "url_count": 10, "robots_txt": "User-agent: *\nAllow: /\n"}
    validation = {"home_url": "https://machinoai.in/", "final_url": HOME + "concepts",
                  "redirects": [HOME, HOME + "concepts"]}
    issues = {f["issue_type"]: f for f in find_issues(crawl, discovery, validation)}

    assert issues["homepage_redirects_to_inner_page"]["severity"] == "medium"
    assert "-> " in issues["homepage_redirects_to_inner_page"]["affected"][0]["value"]
    assert issues["robots_missing_sitemap"]["severity"] == "low"


def test_blocking_answer_engine_crawlers_is_flagged() -> None:
    robots_txt = "User-agent: OAI-SearchBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
    access = crawler_access(robots_txt, HOME)
    assert access["search"]["OAI-SearchBot (ChatGPT search)"] == "blocked"
    assert access["search"]["Googlebot (Google Search)"] == "allowed"

    issues = _issues([_page(HOME)], robots_txt=robots_txt)
    assert issues["search_crawlers_blocked"]["severity"] == "high"


def test_section_health_groups_by_template() -> None:
    pages = [
        _page(HOME + "jobs/location/pune", elapsed_ms=3000, structured_data_types=["ItemList"]),
        _page(HOME + "jobs/location/delhi", elapsed_ms=2000, structured_data_types=["ItemList"]),
        {"url": HOME + "topic/ai", "status_code": 503, "elapsed_ms": 8000},
    ]
    health = {row["template"]: row for row in section_health(pages)}

    assert health["/jobs/*/*"]["pages"] == 2
    assert health["/jobs/*/*"]["median_response_ms"] == 2500
    assert health["/jobs/*/*"]["structured_data"] == ["ItemList"]
    assert health["/topic/*"]["errors"] == 1
