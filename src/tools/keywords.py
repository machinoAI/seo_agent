"""T12 `extract_site_topics` and T15 `score_keyword_opportunities` (design doc §10).

Scoring is a versioned, explainable formula. Missing data is never treated as zero:
queries without enough data get no score and low confidence.
"""

import math
import re
from collections import Counter, defaultdict
from typing import Any
from urllib.parse import urlsplit

from src.persistence.output_store import read_recorded
from src.tools.base import ToolOutput, ToolRequest, ToolStatus, recorded_tool

SCORING_VERSION = "kw-score-v1"
WEIGHTS = {"impressions": 0.40, "ctr_gap": 0.35, "position_opportunity": 0.25}

# Approximate organic CTR by position — a relative benchmark only, not a prediction.
_EXPECTED_CTR = [0.28, 0.15, 0.10, 0.07, 0.05, 0.04, 0.03, 0.025, 0.02, 0.018]

STOPWORDS = frozenset(
    """a about above after again all also am an and any are as at be because been before being
    below between both but by can could did do does doing down during each few for from further
    get got had has have having he her here hers how i if in into is it its itself just let me
    more most my no nor not now of off on once only or other our ours out over own same she
    should so some such than that the their theirs them then there these they this those
    through to too under until up us very was we were what when where which while who whom why
    will with would you your yours home page welcome menu contact login sign blog read more
    new best top get our us via vs""".split()
)
_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.-]*[a-z0-9+#]|[a-z0-9]")


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS and not t.isdigit()]


def expected_ctr(position: float) -> float:
    if position <= 0:
        return _EXPECTED_CTR[0]
    if position <= 10:
        return _EXPECTED_CTR[min(int(round(position)), 10) - 1]
    return 0.01 if position <= 20 else 0.005


def position_opportunity(position: float) -> float:
    """How much ranking headroom a position offers (striking distance scores highest)."""
    if position <= 3:
        return 0.3
    if position <= 10:
        return 1.0
    if position <= 20:
        return 0.8
    if position <= 40:
        return 0.4
    return 0.1


def score_queries(rows: list[dict[str, Any]], limit: int = 150) -> list[dict[str, Any]]:
    """Aggregate Search Console rows per query and compute the v1 opportunity score."""
    per_query: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"clicks": 0, "impressions": 0, "pos_weighted": 0.0, "prev_impressions": 0,
                 "has_previous": False, "pages": Counter()}
    )
    for row in rows:
        q = per_query[row["query"]]
        q["clicks"] += row["clicks"]
        q["impressions"] += row["impressions"]
        q["pos_weighted"] += row["position"] * row["impressions"]
        q["pages"][row["page"]] += row["impressions"]
        if row.get("previous"):
            q["has_previous"] = True
            q["prev_impressions"] += row["previous"]["impressions"]

    if not per_query:
        return []
    max_impressions = max(q["impressions"] for q in per_query.values()) or 1
    scored = []
    for query, q in per_query.items():
        impressions = q["impressions"]
        position = q["pos_weighted"] / impressions if impressions else None
        ctr = q["clicks"] / impressions if impressions else None
        change = None
        if q["has_previous"] and q["prev_impressions"]:
            change = (impressions - q["prev_impressions"]) / q["prev_impressions"]
        declining = change is not None and change < -0.3 and q["prev_impressions"] >= 50

        if position is None or ctr is None:
            score, components = None, None
        else:
            benchmark = expected_ctr(position)
            components = {
                "impressions": round(math.log1p(impressions) / math.log1p(max_impressions), 3),
                "ctr_gap": round(max(0.0, benchmark - ctr) / benchmark, 3),
                "position_opportunity": position_opportunity(position),
            }
            score = round(100 * sum(WEIGHTS[k] * v for k, v in components.items()), 1)

        if declining:
            category = "investigate_decline"
        elif position is not None and position > 20:
            category = "expand_cluster"
        elif components and (position_opportunity(position or 0) >= 0.8
                             or components["ctr_gap"] > 0.3):
            category = "optimize_existing"
        else:
            category = "monitor_trend"

        scored.append({
            "query": query,
            "target_url": q["pages"].most_common(1)[0][0] if q["pages"] else None,
            "clicks": q["clicks"],
            "impressions": impressions,
            "ctr": round(ctr, 4) if ctr is not None else None,
            "avg_position": round(position, 1) if position is not None else None,
            "impressions_change": round(change, 3) if change is not None else None,
            "score": score,
            "score_components": components,
            "score_version": SCORING_VERSION,
            "confidence": (
                "high" if impressions >= 500 else "medium" if impressions >= 100 else "low"
            ),
            "suggested_category": category,
        })
    scored.sort(key=lambda s: (s["score"] is None, -(s["score"] or 0)))
    return scored[:limit]


def extract_topics(
    pages: list[dict[str, Any]], *, brand_tokens: set[str], limit: int = 40
) -> list[dict[str, Any]]:
    """Frequent 1–3 word phrases across page titles and headings (by number of pages)."""
    doc_freq: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    for page in pages:
        texts = [page.get("title") or "", *page.get("h1", []), *page.get("h2", [])]
        phrases: set[str] = set()
        for text in texts:
            tokens = [t for t in tokenize(text) if t not in brand_tokens and len(t) > 2]
            for n in (1, 2, 3):
                phrases.update(" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1))
        for phrase in phrases:
            doc_freq[phrase] += 1
            if len(examples[phrase]) < 3:
                examples[phrase].append(page["url"])

    def rank(item: tuple[str, int]) -> float:
        phrase, count = item
        return count * (1 + 0.5 * (phrase.count(" ")))  # favour specific multi-word phrases

    min_pages = 2 if len(pages) >= 5 else 1
    topics = [(p, c) for p, c in doc_freq.items() if c >= min_pages]
    topics.sort(key=rank, reverse=True)
    return [{"phrase": p, "pages": c, "example_urls": examples[p]} for p, c in topics[:limit]]


class TopicsRequest(ToolRequest):
    crawl_path: str
    max_topics: int = 40


@recorded_tool("extract_site_topics")
def extract_site_topics(request: TopicsRequest) -> ToolOutput:
    crawl = read_recorded(request.crawl_path)["result"].get("data") or {}
    pages = [p for p in crawl.get("pages", []) if p.get("parsed")]
    host = urlsplit(crawl.get("start_url", "")).hostname or request.site
    brand = {label for label in host.removeprefix("www.").split(".")[:-1] if len(label) > 2}
    topics = extract_topics(pages, brand_tokens=brand, limit=request.max_topics)
    return ToolOutput(
        source="crawl_content",
        data={
            "topics": topics,
            "pages_considered": len(pages),
            "method": "title-heading-ngrams-v1",
        },
        warnings=[] if topics else ["Not enough page content to extract topics."],
    )


def find_cannibalization(
    rows: list[dict[str, Any]], *, min_impressions: int = 50, min_share: float = 0.15
) -> list[dict[str, Any]]:
    """Queries where two or more of the site's pages each get a real share of impressions."""
    by_query: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_query[row["query"]].append(row)
    found = []
    for query, query_rows in by_query.items():
        total = sum(r["impressions"] for r in query_rows)
        competing = [r for r in query_rows if total and r["impressions"] / total >= min_share]
        if total >= min_impressions and len(competing) >= 2:
            found.append({
                "query": query,
                "impressions": total,
                "pages": [
                    {"page": r["page"], "impressions": r["impressions"], "clicks": r["clicks"],
                     "position": r["position"]}
                    for r in sorted(competing, key=lambda r: -r["impressions"])
                ],
            })
    return sorted(found, key=lambda f: -f["impressions"])[:30]


def page_trends(rows: list[dict[str, Any]], *, limit: int = 20) -> dict[str, list[dict[str, Any]]]:
    """Per page: clicks/impressions now vs the previous window; top pages and decliners."""
    pages: dict[str, dict[str, int]] = defaultdict(
        lambda: {"clicks": 0, "impressions": 0, "prev_clicks": 0, "prev_impressions": 0}
    )
    for row in rows:
        page = pages[row["page"]]
        page["clicks"] += row["clicks"]
        page["impressions"] += row["impressions"]
        if row.get("previous"):
            page["prev_clicks"] += row["previous"]["clicks"]
            page["prev_impressions"] += row["previous"]["impressions"]
    table = [{"page": url, **v} for url, v in pages.items()]
    declining = [
        {**p, "impressions_change": round((p["impressions"] - p["prev_impressions"])
                                          / p["prev_impressions"], 3)}
        for p in table
        if p["prev_impressions"] >= 100 and p["impressions"] < 0.7 * p["prev_impressions"]
    ]
    return {
        "top_pages": sorted(table, key=lambda p: -p["clicks"])[:limit],
        "declining_pages": sorted(declining, key=lambda p: p["impressions_change"])[:limit],
    }


def quick_wins(scored: list[dict[str, Any]], *, limit: int = 25) -> list[dict[str, Any]]:
    """Queries ranking 4–15 with real impressions: the fastest gains from on-page work."""
    wins = [
        s for s in scored
        if s["avg_position"] is not None and 4 <= s["avg_position"] <= 15
        and s["impressions"] >= 20
    ]
    return sorted(wins, key=lambda s: -s["impressions"])[:limit]


class ScoreRequest(ToolRequest):
    search_path: str
    limit: int = 150


@recorded_tool("score_keyword_opportunities")
def score_keyword_opportunities(request: ScoreRequest) -> ToolOutput:
    result = read_recorded(request.search_path)["result"]
    data = result.get("data")
    if result.get("status") != "success" or not data:
        return ToolOutput(
            source=SCORING_VERSION,
            status=ToolStatus.SKIPPED,
            warnings=["No Search Console data to score; keyword metrics are unavailable."],
        )
    rows = data.get("rows", [])
    opportunities = score_queries(rows, limit=request.limit)
    return ToolOutput(
        source=SCORING_VERSION,
        data={
            "scoring_version": SCORING_VERSION,
            "weights": WEIGHTS,
            "measurement_window": data.get("window"),
            "opportunities": opportunities,
            "quick_wins": quick_wins(opportunities),
            "cannibalization": find_cannibalization(rows),
            **page_trends(rows),
        },
    )
