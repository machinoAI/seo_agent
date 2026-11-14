import gzip

import pytest

from seo_agent.tools.crawling import (
    is_asset,
    normalize_url,
    parse_html,
    parse_robots,
    parse_sitemap,
    stratified_sample,
    template_of,
)

HOSTS = {"machinoai.in", "www.machinoai.in"}


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("HTTPS://Machinoai.IN", "https://machinoai.in/"),
        ("https://machinoai.in:443/a#top", "https://machinoai.in/a"),
        ("https://machinoai.in/a?utm_source=x&id=7", "https://machinoai.in/a?id=7"),
        ("http://machinoai.in:8080/x", "http://machinoai.in:8080/x"),
        ("mailto:hi@machinoai.in", None),
        ("javascript:void(0)", None),
    ],
)
def test_normalize_url(url: str, expected: str | None) -> None:
    assert normalize_url(url) == expected


def test_normalize_url_resolves_relative_links() -> None:
    assert normalize_url("../b?q=1", "https://machinoai.in/x/y/") == "https://machinoai.in/x/b?q=1"


def test_is_asset() -> None:
    assert is_asset("https://machinoai.in/logo.PNG")
    assert not is_asset("https://machinoai.in/services")


@pytest.mark.parametrize(
    ("url", "template"),
    [
        ("https://machinoai.in/", "/"),
        ("https://machinoai.in/jobs", "/jobs"),
        ("https://machinoai.in/jobs/remote", "/jobs/*"),
        ("https://machinoai.in/jobs/location/pune", "/jobs/*/*"),
        ("https://machinoai.in/concepts/rag/some/very/deep/page", "/concepts/*/*"),
    ],
)
def test_template_of(url: str, template: str) -> None:
    assert template_of(url) == template


def test_stratified_sample_covers_every_template_first() -> None:
    base = "https://machinoai.in"
    urls = [f"{base}/jobs/location/c{i}" for i in range(50)] + [
        f"{base}/concepts", f"{base}/concepts/rag/q1", f"{base}/topic/ai", f"{base}/jobs",
    ]
    sample = stratified_sample(urls, 5)

    assert len(sample) == 5
    assert {template_of(u) for u in sample} == {
        "/jobs/*/*", "/concepts", "/concepts/*/*", "/topic/*", "/jobs"
    }


HTML = """<!doctype html>
<html lang="en"><head>
  <title> Machino AI | Automation Services </title>
  <meta name="Description" content="We build AI automation.">
  <meta name="robots" content="index, follow">
  <link rel="canonical" href="/">
  <script type="application/ld+json">
    {"@context": "https://schema.org", "@graph": [{"@type": "Organization"}, {"@type": "WebSite"}]}
  </script>
</head><body>
  <h1>AI automation</h1><h2>Services</h2><h2>Pricing</h2>
  <img src="a.png"><img src="b.png" alt="">
  <a href="/services">Services</a>
  <a href="https://www.machinoai.in/pricing?utm_medium=nav">Pricing</a>
  <a href="https://example.com/">Partner</a>
  <a href="#main">Skip</a><a href="tel:123">Call</a>
  <p>Some words here to count.</p>
</body></html>"""


def test_parse_html_extracts_seo_fields() -> None:
    page = parse_html("https://machinoai.in/", HTML, HOSTS)

    assert page["title"] == "Machino AI | Automation Services"
    assert page["meta_description"] == "We build AI automation."
    assert page["meta_robots"] == "index, follow"
    assert page["canonical"] == "https://machinoai.in/"
    assert page["lang"] == "en"
    assert page["h1"] == ["AI automation"]
    assert page["h2_count"] == 2
    assert page["structured_data_types"] == ["Organization", "WebSite"]
    assert page["images_missing_alt"] == 1  # alt="" is valid for decorative images
    assert page["internal_links"] == [
        "https://machinoai.in/services",
        "https://www.machinoai.in/pricing",
    ]
    assert page["external_link_count"] == 1
    assert page["word_count"] > 5


def test_parse_html_flags_invalid_json_ld() -> None:
    html = '<html><script type="application/ld+json">{not json</script></html>'
    assert parse_html("https://machinoai.in/", html, HOSTS)["structured_data_types"] == [
        "invalid-json-ld"
    ]


SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://machinoai.in/</loc></url>
  <url><loc> https://machinoai.in/services </loc></url>
</urlset>"""

SITEMAP_INDEX = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://machinoai.in/pages.xml</loc></sitemap>
</sitemapindex>"""


def test_parse_sitemap_urlset_index_and_gzip() -> None:
    assert parse_sitemap(SITEMAP) == (
        ["https://machinoai.in/", "https://machinoai.in/services"], []
    )
    assert parse_sitemap(SITEMAP_INDEX) == ([], ["https://machinoai.in/pages.xml"])
    assert parse_sitemap(gzip.compress(SITEMAP))[0][0] == "https://machinoai.in/"
    assert parse_sitemap(b"not xml at all") == ([], [])


def test_parse_sitemap_does_not_expand_external_entities() -> None:
    xxe = b"""<?xml version="1.0"?>
<!DOCTYPE urlset [<!ENTITY x SYSTEM "file:///etc/passwd">]>
<urlset><url><loc>&x;</loc></url></urlset>"""
    urls, _ = parse_sitemap(xxe)
    assert all("root:" not in u for u in urls)


def test_parse_robots() -> None:
    robots = parse_robots(
        "User-agent: *\nDisallow: /admin\nSitemap: https://machinoai.in/sitemap.xml\n"
    )
    assert robots.can_fetch("SEOAgentBot/0.1", "https://machinoai.in/services")
    assert not robots.can_fetch("SEOAgentBot/0.1", "https://machinoai.in/admin/x")
    assert robots.site_maps() == ["https://machinoai.in/sitemap.xml"]
