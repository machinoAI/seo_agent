from typing import Any

from seo_agent.tools.content import match_topics
from seo_agent.tools.keywords import (
    SCORING_VERSION,
    expected_ctr,
    extract_topics,
    find_cannibalization,
    page_trends,
    quick_wins,
    score_queries,
)


def _row(
    query: str, impressions: int, clicks: int, position: float, **extra: Any
) -> dict[str, Any]:
    return {"query": query, "page": "https://machinoai.in/p", "impressions": impressions,
            "clicks": clicks, "ctr": clicks / impressions, "position": position, **extra}


def test_striking_distance_low_ctr_query_scores_highest() -> None:
    scored = score_queries([
        _row("ai automation agency", impressions=2000, clicks=10, position=7.0),
        _row("machinoai", impressions=300, clicks=150, position=1.0),
    ])

    assert scored[0]["query"] == "ai automation agency"
    assert scored[0]["suggested_category"] == "optimize_existing"
    assert scored[0]["confidence"] == "high"
    assert scored[0]["score_version"] == SCORING_VERSION
    assert 0 <= scored[0]["score"] <= 100


def test_declining_query_is_flagged() -> None:
    previous = {"impressions": 1000, "clicks": 50, "position": 4.0}
    scored = score_queries([_row("rpa tools", 300, 5, 9.0, previous=previous)])

    assert scored[0]["impressions_change"] == -0.7
    assert scored[0]["suggested_category"] == "investigate_decline"


def test_no_rows_means_no_scores() -> None:
    assert score_queries([]) == []


def test_cannibalization_needs_two_pages_with_real_share() -> None:
    rows = [
        {**_row("ml jobs", 300, 9, 8.0), "page": "https://machinoai.in/jobs"},
        {**_row("ml jobs", 200, 4, 11.0), "page": "https://machinoai.in/jobs/remote"},
        {**_row("ml jobs", 5, 0, 40.0), "page": "https://machinoai.in/blogs"},
        {**_row("rag", 400, 20, 3.0), "page": "https://machinoai.in/concepts/rag"},
    ]
    found = find_cannibalization(rows)

    assert [f["query"] for f in found] == ["ml jobs"]
    assert [p["page"] for p in found[0]["pages"]] == [
        "https://machinoai.in/jobs", "https://machinoai.in/jobs/remote"
    ]


def test_page_trends_flags_decliners() -> None:
    rows = [
        {**_row("a", 100, 5, 5.0, previous={"impressions": 400, "clicks": 20, "position": 4.0}),
         "page": "https://machinoai.in/jobs"},
        {**_row("b", 500, 50, 2.0, previous={"impressions": 450, "clicks": 40, "position": 2.0}),
         "page": "https://machinoai.in/models"},
    ]
    trends = page_trends(rows)

    assert trends["top_pages"][0]["page"] == "https://machinoai.in/models"
    assert [p["page"] for p in trends["declining_pages"]] == ["https://machinoai.in/jobs"]
    assert trends["declining_pages"][0]["impressions_change"] == -0.75


def test_quick_wins_are_positions_4_to_15_with_impressions() -> None:
    scored = score_queries([
        _row("striking", 900, 10, 6.0),
        _row("top", 900, 300, 1.2),
        _row("deep", 900, 1, 30.0),
        _row("tiny", 5, 0, 7.0),
    ])
    assert [w["query"] for w in quick_wins(scored)] == ["striking"]


def test_expected_ctr_decreases_with_position() -> None:
    assert expected_ctr(1) > expected_ctr(5) > expected_ctr(15) > expected_ctr(50)


PAGES = [
    {"url": "https://machinoai.in/ai-automation", "title": "AI Automation Services",
     "h1": ["AI automation"], "h2": ["Workflow automation"]},
    {"url": "https://machinoai.in/chatbots", "title": "Custom Chatbots",
     "h1": ["AI chatbots"], "h2": ["Workflow automation"]},
    {"url": "https://machinoai.in/about", "title": "About Machinoai", "h1": ["About"], "h2": []},
]


def test_extract_topics_skips_brand_and_stopwords() -> None:
    topics = {t["phrase"]: t["pages"] for t in extract_topics(PAGES, brand_tokens={"machinoai"})}

    assert topics["workflow automation"] == 2
    assert "machinoai" not in topics
    assert "about" not in topics  # stopword


def test_match_topics_reports_coverage() -> None:
    matches = {m["topic"]: m for m in match_topics(["ai automation", "quantum computing"], PAGES)}

    assert matches["ai automation"]["coverage"] == "strong"
    assert matches["ai automation"]["best_matches"][0]["url"].endswith("/ai-automation")
    assert matches["quantum computing"]["coverage"] == "none"
