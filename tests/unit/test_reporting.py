from seo_agent.tools.performance import extract_pagespeed, select_priority_urls
from seo_agent.tools.reporting import (
    action_plan_rows,
    finding_rows,
    page_rows,
    render_markdown,
)

HOME = "https://www.machinoai.in/"
TECHNICAL = {
    "findings": [{
        "issue_type": "slow_server_response", "severity": "medium", "affected_count": 2,
        "affected": [{"url": HOME + "jobs", "value": "4006 ms"},
                     {"url": HOME + "jobs/remote", "value": "2999 ms"}],
    }],
    "section_health": [{"template": "/jobs/*", "pages": 2, "errors": 0,
                        "median_response_ms": 3500, "max_response_ms": 4006,
                        "median_words": 750, "missing_h1": 0,
                        "structured_data": ["CollectionPage"]}],
}
AUDIT = {"findings": [
    {"issue_type": "slow_server_response", "severity": "high", "affected_count": 2,
     "recommended_action": "Cache | jobs pages at the edge", "owner": "developer",
     "done_when": "HTML under 800 ms"},
    {"issue_type": "missing_expected_schema", "severity": "high", "affected_count": 1,
     "example_urls": [HOME + "jobs/123"], "evidence": "No JobPosting",
     "recommended_action": "Add JobPosting", "owner": "developer",
     "done_when": "Rich result test passes"},
]}
REPORT = {
    "report_type": "baseline",
    "is_complete": False,
    "executive_summary": "Baseline established.",
    "action_plan": [
        {"priority": "p2", "action": "Shorten titles", "urls": [HOME + "models"],
         "owner": "content", "effort": "small", "impact": "low"},
        {"priority": "p1", "action": "Cache job pages", "template": "/jobs/*",
         "urls": [HOME + "jobs"], "owner": "developer", "effort": "medium", "impact": "high",
         "why": "Median 3.5 s", "done_when": "HTML under 800 ms"},
    ],
    "sections": {"technical_health": "Two issues."},
    "data_gaps": ["LLM restated gap"],
}


def test_report_leads_with_coverage_and_prioritized_action_plan() -> None:
    markdown = render_markdown(
        site="machinoai.in", run_id="r1", run_date="2026-11-14", report=REPORT, audit=AUDIT,
        keywords=None, content=None, agents=[{"agent": "seo_audit", "status": "succeeded"}],
        data_gaps=["No trend source", "No trend source"],
        coverage={"sitemap_urls": 2720, "pages_fetched": 20, "html_pages_analyzed": 19,
                  "error_pages": 1, "share_of_sitemap": "0.7%"},
        sources={"Search Console": "not configured"},
        technical=TECHNICAL, files=["findings.csv"],
    )

    assert "20 of 2,720 sitemap URLs fetched (0.7%)" in markdown
    assert "Search Console: not configured" in markdown
    assert markdown.index("Cache job pages") < markdown.index("Shorten titles")  # p1 first
    assert "Done when: HTML under 800 ms" in markdown
    assert "## Template health" in markdown and "3500 ms" in markdown
    assert f"{HOME}jobs (4006 ms)" in markdown  # measured values next to URLs
    assert "Cache \\| jobs pages" in markdown  # pipes escaped inside tables
    assert markdown.count("- No trend source") == 1  # gaps de-duplicated
    assert "LLM restated gap" not in markdown  # only tool-reported gaps are listed
    assert "`findings.csv`" in markdown


def test_legacy_next_actions_still_render() -> None:
    markdown = render_markdown(
        site="machinoai.in", run_id="r1", run_date="2026-11-14",
        report={"executive_summary": "x", "next_actions": ["Fix titles"]},
        audit=None, keywords=None, content=None, agents=[], data_gaps=[],
    )
    assert "1. Fix titles" in markdown


def test_csv_rows_merge_rule_values_with_agent_review() -> None:
    rows = finding_rows(TECHNICAL, AUDIT)

    assert rows[0] == ["high", "slow_server_response", HOME + "jobs", "4006 ms",
                       "Cache | jobs pages at the edge", "developer", "HTML under 800 ms"]
    assert len(rows) == 3  # 2 rule rows + 1 agent-only finding
    assert rows[2][1] == "missing_expected_schema" and rows[2][2] == HOME + "jobs/123"
    assert [r[1] for r in action_plan_rows(REPORT)] == ["p1", "p2"]
    page = {"url": HOME + "jobs", "status_code": 200, "elapsed_ms": 4006, "title": "Jobs",
            "h1": ["AI Jobs"], "internal_links": [HOME]}
    assert page_rows({"pages": [page]})[0][:4] == [HOME + "jobs", "/jobs", 200, 4006]


def test_report_without_llm_output_still_renders() -> None:
    markdown = render_markdown(
        site="machinoai.in", run_id="r1", run_date="2026-11-14", report=None,
        audit=None, keywords=None, content=None, agents=[], data_gaps=[],
    )
    assert "did not produce a summary" in markdown


def test_extract_pagespeed_separates_lab_and_field() -> None:
    payload = {
        "lighthouseResult": {
            "categories": {"performance": {"score": 0.62}},
            "audits": {
                "largest-contentful-paint": {"numericValue": 3200.4},
                "render-blocking-resources": {
                    "title": "Eliminate render-blocking resources",
                    "score": 0.3,
                    "details": {"overallSavingsMs": 850},
                },
            },
        },
        "loadingExperience": {"origin_fallback": True, "metrics": {}},
        "originLoadingExperience": {
            "overall_category": "AVERAGE",
            "metrics": {"CUMULATIVE_LAYOUT_SHIFT_SCORE": {"percentile": 12}},
        },
    }
    data = extract_pagespeed(payload, "https://machinoai.in/", "mobile")

    assert data["lab"]["performance_score"] == 62
    assert data["lab"]["lcp_ms"] == 3200.4
    assert data["field"] is None  # URL-level data missing: origin fallback is not URL data
    assert data["origin_field"]["p75"]["cls"] == 0.12
    assert data["top_savings"][0]["savings_ms"] == 850


def test_priority_urls_start_with_homepage_then_most_linked() -> None:
    home = "https://machinoai.in/"
    crawl = {
        "start_url": home,
        "pages": [
            {"url": home, "parsed": True, "internal_links": [home + "b", home + "a"]},
            {"url": home + "a", "parsed": True, "internal_links": [home + "b"]},
            {"url": home + "b", "parsed": True, "internal_links": []},
        ],
    }
    assert select_priority_urls(crawl, 2) == [home, home + "b"]
