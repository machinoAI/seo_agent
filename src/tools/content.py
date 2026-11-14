"""T16 (lexical v1) `match_topics_to_pages`: map keywords/topics to existing pages.

Scores word overlap with each page's title, H1, URL path and H2s. This is the
no-dependency first version; semantic retrieval with embeddings (ChromaDB, Phase 4)
replaces it. Overlap is a hint, not proof of the same search intent.
"""

from typing import Any
from urllib.parse import urlsplit

from src.persistence.output_store import read_recorded
from src.tools.base import ToolOutput, ToolRequest, recorded_tool
from src.tools.keywords import tokenize

MATCH_VERSION = "lexical-v1"
FIELD_WEIGHTS = {"title": 3.0, "h1": 2.0, "url": 2.0, "h2": 1.0}
STRONG, PARTIAL = 0.5, 0.2


def _page_fields(page: dict[str, Any]) -> dict[str, set[str]]:
    path = urlsplit(page["url"]).path.replace("-", " ").replace("_", " ").replace("/", " ")
    return {
        "title": set(tokenize(page.get("title") or "")),
        "h1": set(tokenize(" ".join(page.get("h1", [])))),
        "url": set(tokenize(path)),
        "h2": set(tokenize(" ".join(page.get("h2", [])))),
    }


def match_topics(
    topics: list[str], pages: list[dict[str, Any]], top_n: int = 3
) -> list[dict[str, Any]]:
    indexed = [(page, _page_fields(page)) for page in pages]
    max_weight = sum(FIELD_WEIGHTS.values())
    results = []
    for topic in topics:
        terms = set(tokenize(topic))
        if not terms:
            continue
        scored = []
        for page, fields in indexed:
            raw = sum(
                FIELD_WEIGHTS[name] * len(terms & tokens) / len(terms)
                for name, tokens in fields.items()
            )
            if raw > 0:
                scored.append((round(raw / max_weight, 3), page))
        scored.sort(key=lambda item: -item[0])
        best = scored[0][0] if scored else 0.0
        results.append({
            "topic": topic,
            "coverage": "strong" if best >= STRONG else "partial" if best >= PARTIAL else "none",
            "best_matches": [
                {"url": page["url"], "title": page.get("title"), "score": score}
                for score, page in scored[:top_n]
            ],
        })
    return results


class MatchRequest(ToolRequest):
    crawl_path: str
    topics: list[str]


@recorded_tool("match_topics_to_pages")
def match_topics_to_pages(request: MatchRequest) -> ToolOutput:
    crawl = read_recorded(request.crawl_path)["result"].get("data") or {}
    pages = [p for p in crawl.get("pages", []) if p.get("parsed")]
    matches = match_topics(request.topics, pages)
    return ToolOutput(
        source=MATCH_VERSION,
        data={
            "method": MATCH_VERSION,
            "matches": matches,
            "gaps": [m["topic"] for m in matches if m["coverage"] == "none"],
        },
        warnings=["Lexical matching only; semantic retrieval arrives with embeddings (Phase 4)."],
    )
