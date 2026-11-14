"""T22 `generate_report`: render the run as `report.md` plus CSV exports in the run folder.

    report.md        what to do and why: coverage, action plan, alerts, template health,
                     URL-level findings, keywords, content plan, data gaps
    action_plan.csv  one row per action (priority, URLs, owner, effort, impact, done when)
    findings.csv     one row per affected URL per issue, with the measured value
    pages.csv        page inventory: status, speed, title, description, H1, words, schema
"""

import csv
from pathlib import Path
from typing import Any

from src.persistence.output_store import read_result_data
from src.tools.base import ToolOutput, ToolRequest, recorded_tool
from src.tools.crawling import template_of

PRIORITY_ORDER = {"p1": 0, "p2": 1, "p3": 2}


def _cell(value: Any, limit: int = 300) -> str:
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value)
    text = "" if value is None else str(value)
    text = text.replace("|", "\\|").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    if not rows:
        return ["_None._", ""]
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(_cell(v) for v in row) + " |" for row in rows]
    return [*lines, ""]


def _coverage_line(coverage: dict[str, Any], sources: dict[str, str]) -> str:
    parts = []
    if coverage:
        fetched = coverage.get("pages_fetched", 0)
        total = coverage.get("sitemap_urls")
        share = f" ({coverage['share_of_sitemap']})" if coverage.get("share_of_sitemap") else ""
        scope = f"{fetched} of {total:,} sitemap URLs fetched{share}" if total else (
            f"{fetched} pages fetched")
        parts.append(f"{scope}: {coverage.get('html_pages_analyzed', 0)} HTML pages analysed, "
                     f"{coverage.get('error_pages', 0)} returned errors")
        health = coverage.get("crawl_health") or {}
        if health.get("stopped_early"):
            parts.append(
                f"**crawl stopped early**: the site kept returning server errors (first after "
                f"{health.get('first_server_error_after_pages')} pages); "
                f"{health.get('not_crawled', 0)} queued pages not crawled"
            )
        elif health.get("server_errors"):
            parts.append(f"crawler slowed down to {health.get('max_delay_s')} s between requests "
                         f"after {health['server_errors']} server errors")
    parts += [f"{name}: {status}" for name, status in sources.items()]
    return " · ".join(parts)


def cost_summary(agents: list[dict[str, Any]]) -> dict[str, Any]:
    """Total LLM usage and estimated cost across the run's agents."""
    totals: dict[str, Any] = {
        "llm_calls": 0, "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0,
        "reasoning_tokens": 0, "cost_usd": 0.0, "unpriced_models": [],
    }
    for agent in agents:
        usage = agent.get("usage") or {}
        for key in ("llm_calls", "input_tokens", "cached_input_tokens", "output_tokens",
                    "reasoning_tokens"):
            totals[key] += int(usage.get(key) or 0)
        if usage.get("cost_usd") is not None:
            totals["cost_usd"] += usage["cost_usd"]
        elif usage.get("llm_calls") and agent.get("model"):
            totals["unpriced_models"].append(agent["model"])
    totals["cost_usd"] = round(totals["cost_usd"], 4)
    totals["models"] = sorted({a["model"] for a in agents if a.get("model")})
    return totals


def _money(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"${value:.4f}" if value < 1 else f"${value:,.2f}"


def _cost_line(cost: dict[str, Any]) -> str:
    if not cost.get("llm_calls"):
        return "no LLM calls recorded"
    line = (
        f"**{_money(cost['cost_usd'])}** estimated LLM spend · {cost['llm_calls']} calls on "
        f"{', '.join(cost['models'])} · {cost['input_tokens']:,} input tokens "
        f"({cost['cached_input_tokens']:,} cached) · {cost['output_tokens']:,} output tokens"
    )
    if cost.get("reasoning_tokens"):
        line += f" (incl. {cost['reasoning_tokens']:,} reasoning)"
    if cost.get("unpriced_models"):
        line += (f" · price unknown for {', '.join(sorted(set(cost['unpriced_models'])))}: "
                 "add it to LLM_PRICES")
    return line + " · crawling, PageSpeed and Search Console are free"


def _audit_lookup(audit: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {f.get("issue_type", ""): f for f in (audit or {}).get("findings", [])}


def _examples(finding: dict[str, Any], technical: dict[str, dict[str, Any]], n: int = 3) -> str:
    rule = technical.get(finding.get("issue_type", ""))
    if rule and rule.get("affected"):
        return "; ".join(
            f"{a['url']}" + (f" ({a['value']})" if a.get("value") not in (None, "") else "")
            for a in rule["affected"][:n]
        )
    return ", ".join(finding.get("example_urls", [])[:n])


def render_markdown(
    *,
    site: str,
    run_id: str,
    run_date: str,
    report: dict[str, Any] | None,
    audit: dict[str, Any] | None,
    keywords: dict[str, Any] | None,
    content: dict[str, Any] | None,
    agents: list[dict[str, Any]],
    data_gaps: list[str],
    coverage: dict[str, Any] | None = None,
    sources: dict[str, str] | None = None,
    technical: dict[str, Any] | None = None,
    files: list[str] | None = None,
) -> str:
    report = report or {}
    technical = technical or {}
    rules = {f["issue_type"]: f for f in technical.get("findings", [])}
    complete = report.get("is_complete", False)
    lines = [
        f"# SEO & AEO report: {site}",
        "",
        f"Run `{run_id}` · {run_date} · {report.get('report_type', 'baseline')} · "
        f"{'complete' if complete else '**partial**'}",
        "",
    ]
    cost = cost_summary(agents)
    lines += [f"> **Cost:** {_cost_line(cost)}", ">"]
    if coverage or sources:
        lines += [f"> **Coverage:** {_coverage_line(coverage or {}, sources or {})}"]
    lines.append("")
    lines += [
        "## Executive summary",
        "",
        report.get("executive_summary") or "_The reporting agent did not produce a summary._",
        "",
    ]

    actions = sorted(report.get("action_plan") or [],
                     key=lambda a: PRIORITY_ORDER.get(a.get("priority", "p3"), 3))
    lines += ["## Action plan", ""]
    if actions:
        lines += _table(
            ["#", "Priority", "Action", "Pages / template", "Owner", "Effort", "Impact"],
            [[i, a.get("priority"), a.get("action"),
              a.get("template") or ", ".join(a.get("urls", [])[:3]),
              a.get("owner"), a.get("effort"), a.get("impact")]
             for i, a in enumerate(actions, 1)],
        )
        for i, action in enumerate(actions, 1):
            lines.append(f"**{i}. {action.get('action')}**")
            if action.get("why"):
                lines.append(f"- Why: {action['why']}")
            if action.get("urls"):
                lines.append("- Pages: " + ", ".join(action["urls"][:10]))
            if action.get("done_when"):
                lines.append(f"- Done when: {action['done_when']}")
            lines.append("")
    else:
        legacy = report.get("next_actions") or []
        lines += [f"{i}. {a}" for i, a in enumerate(legacy, 1)] or ["_None._"]
        lines.append("")

    alerts = report.get("alerts") or []
    if alerts:
        lines += ["## Alerts", ""]
        lines += _table(["Severity", "Type", "Detail"],
                        [[a.get("severity"), a.get("type"), a.get("detail")] for a in alerts])

    health = technical.get("section_health") or []
    if health:
        lines += ["## Template health", ""]
        lines += _table(
            ["Template", "Pages", "Errors", "Median response", "Max response", "Median words",
             "No H1", "Structured data"],
            [[h["template"], h["pages"], h["errors"],
              f"{h['median_response_ms']} ms" if h.get("median_response_ms") else "",
              f"{h['max_response_ms']} ms" if h.get("max_response_ms") else "",
              h.get("median_words"), h.get("missing_h1"), h.get("structured_data")]
             for h in health],
        )

    if audit:
        lines += ["## Technical findings", ""]
        lines += _table(
            ["Severity", "Issue", "Pages", "Examples (measured)", "Fix", "Owner", "Done when"],
            [[f.get("severity"), f.get("issue_type"), f.get("affected_count"),
              _examples(f, rules), f.get("recommended_action"), f.get("owner"),
              f.get("done_when")]
             for f in audit.get("findings", [])[:30]],
        )
    if keywords:
        lines += ["## Keyword opportunities", ""]
        lines += _table(
            ["Keyword", "Category", "Impr.", "Clicks", "Pos.", "Score", "Target URL", "Action"],
            [[o.get("keyword"), o.get("category"), (o.get("metrics") or {}).get("impressions"),
              (o.get("metrics") or {}).get("clicks"), (o.get("metrics") or {}).get("avg_position"),
              o.get("score"), o.get("target_url"), o.get("recommended_action")]
             for o in keywords.get("opportunities", [])[:20]],
        )
        if keywords.get("cannibalization"):
            lines += ["### Pages competing for the same query", ""]
            lines += _table(
                ["Query", "Keep", "Other pages", "Action"],
                [[c.get("query"), c.get("keep_url"), c.get("other_urls"), c.get("action")]
                 for c in keywords["cannibalization"]],
            )
    if content:
        lines += ["## Content recommendations", ""]
        lines += _table(
            ["Priority", "Action", "Topic", "Target URL", "Proposed title", "Success criteria"],
            [[r.get("priority"), r.get("action"), r.get("target_keyword"), r.get("target_url"),
              r.get("proposed_title"), r.get("success_criteria")]
             for r in content.get("recommendations", [])[:15]],
        )
        lines += ["_Full briefs (outline, questions, internal links, schema) are in the "
                  "`agent_content_strategy` JSON file in this folder._", ""]

    sections = report.get("sections") or {}
    if sections:
        lines += ["## Details", ""]
        for name, text in sections.items():
            lines += [f"### {name.replace('_', ' ').capitalize()}", "", str(text or "_No data._"),
                      ""]

    lines += ["## Data gaps", ""]
    gaps = list(dict.fromkeys(data_gaps))  # tool-reported gaps, exact and de-duplicated
    lines += [f"- {g}" for g in gaps] or ["_None reported._"]
    if files:
        lines += ["", "## Files in this run", ""]
        lines += [f"- `{name}`" for name in files]
    lines += ["", "## Run details", ""]

    def usage(agent: dict[str, Any], key: str) -> str:
        value = (agent.get("usage") or {}).get(key)
        return f"{value:,}" if isinstance(value, int) else ""

    rows = [[a.get("agent"), a.get("status"), a.get("model"), a.get("reasoning"),
             a.get("prompt_ref"), usage(a, "llm_calls"), usage(a, "input_tokens"),
             usage(a, "output_tokens"), _money((a.get("usage") or {}).get("cost_usd"))]
            for a in agents]
    if agents:
        rows.append(["**Total**", "", "", "", "", f"{cost['llm_calls']:,}",
                     f"{cost['input_tokens']:,}", f"{cost['output_tokens']:,}",
                     f"**{_money(cost['cost_usd'])}**"])
    lines += _table(
        ["Agent", "Status", "Model", "Reasoning", "Prompt", "LLM calls", "Input tokens",
         "Output tokens", "Est. cost"],
        rows,
    )
    lines.append(
        "_Costs are estimates from token counts and list prices (see `llm/pricing.py`); the "
        "provider's invoice is authoritative. Observed metrics come from the tools recorded in "
        "this run folder; recommendations and expected outcomes are estimates, not guarantees._"
    )
    return "\n".join(lines) + "\n"


# ── CSV exports ──────────────────────────────────────────────────────────────


def _write_csv(path: Path, headers: list[str], rows: list[list[Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(
            [", ".join(map(str, v)) if isinstance(v, list) else v for v in row] for row in rows
        )


def action_plan_rows(report: dict[str, Any] | None) -> list[list[Any]]:
    actions = sorted((report or {}).get("action_plan") or [],
                     key=lambda a: PRIORITY_ORDER.get(a.get("priority", "p3"), 3))
    return [[i, a.get("priority"), a.get("action"), a.get("template"), " ".join(a.get("urls", [])),
             a.get("owner"), a.get("effort"), a.get("impact"), a.get("why"), a.get("done_when"),
             a.get("source")] for i, a in enumerate(actions, 1)]


def finding_rows(
    technical: dict[str, Any] | None, audit: dict[str, Any] | None
) -> list[list[Any]]:
    """One row per affected URL; the agent's severity/fix/owner override the rule defaults."""
    reviewed = _audit_lookup(audit)
    rows = []
    for rule in (technical or {}).get("findings", []):
        review = reviewed.get(rule["issue_type"], {})
        for item in rule.get("affected", []):
            rows.append([review.get("severity", rule["severity"]), rule["issue_type"],
                         item["url"], item.get("value"), review.get("recommended_action", ""),
                         review.get("owner", ""), review.get("done_when", "")])
    covered = {r["issue_type"] for r in (technical or {}).get("findings", [])}
    for issue, review in reviewed.items():  # findings added by the agent (e.g. missing schema)
        if issue not in covered:
            for url in review.get("example_urls", []) or [""]:
                rows.append([review.get("severity"), issue, url, review.get("evidence"),
                             review.get("recommended_action"), review.get("owner"),
                             review.get("done_when")])
    return rows


def page_rows(crawl: dict[str, Any] | None) -> list[list[Any]]:
    rows = []
    for p in (crawl or {}).get("pages", []):
        rows.append([
            p["url"], template_of(p["url"]), p.get("status_code") or p.get("error"),
            p.get("elapsed_ms"), p.get("title"), p.get("title_length"),
            p.get("description_length"), p.get("h1_count"), " | ".join(p.get("h1", [])[:2]),
            p.get("word_count"), p.get("canonical"), p.get("meta_robots"),
            p.get("structured_data_types"), len(p.get("internal_links", [])),
        ])
    return rows


class ReportRequest(ToolRequest):
    output_dir: str
    run_date: str
    report: dict[str, Any] | None = None
    audit: dict[str, Any] | None = None
    keywords: dict[str, Any] | None = None
    content: dict[str, Any] | None = None
    agents: list[dict[str, Any]] = []
    coverage: dict[str, Any] = {}
    sources: dict[str, str] = {}
    data_gaps: list[str] = []
    crawl_path: str | None = None
    technical_path: str | None = None


@recorded_tool("generate_report")
def generate_report(request: ReportRequest) -> ToolOutput:
    folder = Path(request.output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    technical = read_result_data(request.technical_path) if request.technical_path else None
    crawl = read_result_data(request.crawl_path) if request.crawl_path else None

    files: dict[str, Path] = {}
    exports = {
        "action_plan.csv": (
            ["#", "priority", "action", "template", "urls", "owner", "effort", "impact", "why",
             "done_when", "source"],
            action_plan_rows(request.report),
        ),
        "findings.csv": (
            ["severity", "issue_type", "url", "measured_value", "recommended_action", "owner",
             "done_when"],
            finding_rows(technical, request.audit),
        ),
        "pages.csv": (
            ["url", "template", "status", "response_ms", "title", "title_length",
             "description_length", "h1_count", "h1", "word_count", "canonical", "meta_robots",
             "structured_data", "internal_links"],
            page_rows(crawl),
        ),
    }
    for name, (headers, rows) in exports.items():
        if rows:
            files[name] = folder / name
            _write_csv(files[name], headers, rows)

    markdown = render_markdown(
        site=request.site,
        run_id=str(request.run_id),
        run_date=request.run_date,
        report=request.report,
        audit=request.audit,
        keywords=request.keywords,
        content=request.content,
        agents=request.agents,
        data_gaps=request.data_gaps,
        coverage=request.coverage,
        sources=request.sources,
        technical=technical,
        files=list(files),
    )
    report_path = folder / "report.md"
    report_path.write_text(markdown, encoding="utf-8")
    return ToolOutput(
        source="report_renderer",
        data={"report_path": str(report_path), "files": {k: str(v) for k, v in files.items()}},
    )
