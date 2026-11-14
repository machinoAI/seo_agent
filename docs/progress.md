# Development Progress

Living tracker for the SEO + AEO Growth Agent. Update it with every change.
Design reference: [`../seo_aeo_growth_agent_design.md`](../seo_aeo_growth_agent_design.md) (section numbers below point there).

**Last updated:** 2026-11-14 (precise, actionable reports + Search Console analysis)

---

## Status at a glance

| Phase (doc §18) | Status | Notes |
|---|---|---|
| 1 — Foundation | **Done** | API, config, local database + migrations, LangGraph workflow with checkpoints, logging, LLM layer, prompts, tool contract. Runs without Docker. |
| 2 — Website Audit | **Mostly done** | robots/sitemaps, crawler, technical checks, PageSpeed lab + field data, baseline report. Pending: JS rendering (Playwright), fixture-based acceptance tests. |
| 3 — Search & Trend Intelligence | **Partly done** | Search Console (when configured), versioned scoring, site topics. Pending: trend source, keyword-provider data, competitor analysis. |
| 4 — Content Strategy | **Partly done** | Lexical page matching + LLM briefs. Pending: embeddings / semantic retrieval (ChromaDB embedded), approval workflow. |
| 5 — Monitoring & Reporting | **Partly done** | Markdown report per run, history comparison via the database. Pending: scheduler, recurring runs, monthly report, alerts delivery. |
| 6 — Production Hardening | Not started | API key auth exists; see Pending. |

---

## How to run

Requires **Python 3.12** (`.python-version`).

```bash
bash scripts/setup_env.sh    # creates .venv312 with Python 3.12, installs, runs the tests
source .venv312/bin/activate
seo-agent --check-llm        # verify LLM key/model
seo-agent --max-pages 50     # quick run on TARGET_SITE (machinoai.in)
```

Output: `data/output/<site>/<YYYY-MM-DD>/run_<run_id>/` (every tool call + agent output as JSON, `manifest.jsonl`, `report.md`).

---

## Done

| Area | Files | Description |
|---|---|---|
| Local-first storage | `config.py`, `persistence/database.py`, `persistence/models.py`, `persistence/repositories.py` | SQLite file (`data/seo_agent.db`) by default: no Docker, Postgres, Redis or Chroma server needed. Tables: `websites`, `workflow_runs`, `agent_results`. PostgreSQL supported via `DATABASE_URL` + `.[postgres]` extra. |
| Migrations | `alembic.ini`, `migrations/env.py`, `migrations/versions/20261114_0001_initial_schema.py` | Applied automatically at startup when `AUTO_MIGRATE=true`. Autogenerate ignores LangGraph's own tables. |
| Workflow | `orchestration/state.py`, `graph.py`, `workflow.py` | LangGraph: validate_site → seo_audit → keyword_research → content_strategy → performance_reporting, with conditional routing (unreachable site stops; no pages crawled skips keyword/content). Every step is isolated: a failure is recorded and the run continues. SQLite checkpoints make runs resumable (`--resume`). |
| Agents | `agents/base.py`, `seo_audit.py`, `keyword_research.py`, `content_strategy.py`, `performance_reporting.py` | Each agent runs its tools, then its LLM analyses the evidence with its YAML prompt. Replies are validated against a Pydantic schema; one correction retry. Output saved to the run folder and the database. Previous runs feed change detection and avoid duplicate recommendations. |
| Domain validation & safe HTTP | `tools/domain.py`, `tools/http.py` | Public-IP-only DNS checks (blocks private, loopback, link-local, metadata, IPv4-mapped), standard ports only, redirects re-validated, credentials dropped on cross-host redirects, size caps, per-request and overall timeouts, retries with backoff and Retry-After. |
| Crawling | `tools/crawling.py` | robots.txt + sitemaps (incl. indexes, gzip, XXE-safe), concurrent same-site crawl that respects robots.txt and the page budget, page extraction (title, description, headings, canonical, robots, lang, JSON-LD/microdata, links, images, word count). |
| Technical checks | `tools/technical_seo.py` | 28 deterministic rules (`tech-rules-v2`), each with measured values per URL: HTTP errors, broken internal links, redirect chains, noindex, canonicals, titles, descriptions, H1s, thin content, structured data, alt text, lang, slow responses, robots/sitemap problems. |
| Performance | `tools/performance.py` | PageSpeed Insights: Lighthouse lab metrics and CrUX field data (URL and origin) for priority pages. No local Chrome needed. |
| Search & keywords | `tools/search_console.py`, `tools/keywords.py` | Search Console (service account; current vs previous window). Versioned score `kw-score-v1` (impressions, CTR gap vs position benchmark, position headroom) with components and confidence. Site topics from titles/headings. |
| Content matching | `tools/content.py` | Keyword/topic → existing-page matching (`lexical-v1`) with coverage strong / partial / none. |
| Report | `tools/reporting.py` | `report.md` per run: summary, alerts, sections, findings, keywords, content plan, next actions, data gaps, run details. Rendered even if the reporting LLM fails. |
| API | `main.py`, `api/routes/health.py`, `api/routes/runs.py`, `api/schemas.py` | `POST /runs` (validates domain incl. DNS, starts the run in the background, max 2 concurrent), `GET /runs/{id}`, `/health/live`, `/health/ready`. Optional `API_KEY` (X-API-Key header). |
| CLI runner | `runner.py` | `seo-agent` with `--site`, `--max-pages`, `--provider`, `--model`, `--reasoning`, `--check-llm`, `--resume`. Prints the plan, progress summary and report path. |
| Logging | `observability/logging.py` | structlog; JSON in production; run/site/step context on every line; sensitive keys redacted. |
| LLM layer | `llm/` | OpenAI, Anthropic, Gemini, Inception (Mercury); global / per-agent / per-run switching of provider, model and reasoning. |
| Prompts | `prompts/*.yaml` | One versioned, XML-tagged YAML per agent (v2: analyse provided evidence) + `shared.yaml` (correction snippet). |
| Tool recording | `tools/base.py`, `persistence/output_store.py` | Every tool call (and failure) saved as JSON under the run folder, which keeps its start date for the whole run. |
| Run cost | `llm/pricing.py`, `agents/base.py`, `tools/reporting.py`, migration `0002` | Token usage of every LLM call (incl. correction retries, cached and reasoning tokens) is recorded per agent with an estimated USD cost from list prices (Nov 2026; promos switch to regular price after their end date; `LLM_PRICES` in `.env` adds or overrides models). `report.md` shows the total on top and a per-agent breakdown in Run details; the runner prints it; stored in `agent_results.usage` and the run summary. |
| Actionable reports | `tools/reporting.py`, `agents/performance_reporting.py`, prompts v3 | `report.md` opens with a coverage line (sitemap size vs pages fetched, data-source status) and a prioritized **action plan** (priority, URLs/template, owner, effort, impact, why, done-when). Adds template health, measured values next to every example URL, de-duplicated tool-reported data gaps, and CSV exports: `action_plan.csv`, `findings.csv` (one row per URL per issue), `pages.csv` (page inventory). |
| Precise audit | `tools/technical_seo.py` (`tech-rules-v2`), `tools/crawling.py`, `agents/seo_audit.py` | Every finding lists affected URLs with the measured value. New checks: homepage redirecting to an inner page, robots.txt without a `Sitemap:` line, search/AI-answer crawlers blocked by robots.txt. Per-template health (speed, words, H1, structured data). The crawl samples sitemap URLs evenly across templates instead of taking the first ones; full sitemap size is counted. The audit agent checks expected schema per page type (e.g. JobPosting) and gives owner, effort and done-when per finding. |
| Search Console analysis | `tools/search_console.py`, `tools/keywords.py`, `agents/keyword_research.py`, `runner.py` | Up to 5,000 query×page rows; quick wins (positions 4–15), cannibalization (queries split across pages), declining and top pages; keyword agent names the page and the change. `seo-agent --check-sources` shows the service-account email, readable properties and the PageSpeed status. |
| Python 3.12 environment | `.python-version`, `scripts/setup_env.sh`, `pyproject.toml` | Python pinned to 3.12. One script creates `.venv312` on 3.12 via uv (downloads Python if needed) or `python3.12`, leaves an existing `.venv` alone, installs the project with dev tools and runs the tests. Code checked for 3.12: no removed or deprecated APIs, no 3.13-only features. |
| Config & secrets | `.env`, `.env.example` | Target site and all keys at the top; Postgres/Redis/Chroma sections removed; database, data-source and API-key settings added. |
| Container (optional) | `Dockerfile`, `docker-compose.yml` | Single API container with a data volume, bound to localhost. Optional Postgres profile. |
| Tests | `tests/unit/` (10 files), `tests/integration/test_api.py` | 105 unit cases: cost estimates, crawler parsing, template sampling, sitemap/XXE, SSRF checks, technical rules, scoring, page matching, PageSpeed extraction, report rendering, JSON validation + correction, prompts, LLM factory, tool recording. API smoke tests with a temp database. |

### LLM layer: how switching works

- **Global default:** `LLM_PROVIDER`, `LLM_MODEL`, `LLM_REASONING` in `.env`.
- **Per agent:** `<AGENT>_LLM_PROVIDER / _MODEL / _REASONING` (agents: `SEO_AUDIT`, `KEYWORD_RESEARCH`, `CONTENT_STRATEGY`, `PERFORMANCE_REPORTING`).
- **Per run:** `--provider / --model / --reasoning` on the runner, or the same fields on `POST /runs`.
- Switching provider without naming a model uses that provider's default: `gpt-5.5`, `claude-sonnet-5-5`, `gemini-3.8-flash`, `mercury-3`.

| `LLM_REASONING` | OpenAI | Anthropic | Gemini | Inception |
|---|---|---|---|---|
| `default` | nothing sent | thinking off | nothing sent | nothing sent |
| `none` | `none` | thinking off | `low` (Gemini 3+ can't turn thinking off) | `instant` |
| `low` / `medium` / `high` | same | adaptive thinking + effort | `thinking_level` | same |
| Native extras | `minimal`, `xhigh`, `max` | `xhigh`, `max` | `minimal` | `instant` |

### Design decisions

- **Local-first storage.** SQLite replaces PostgreSQL by default; Redis isn't needed yet (no shared cache or locks with a single process); ChromaDB will run embedded from `data/` when semantic retrieval lands. PostgreSQL remains a supported production setting.
- **Tools run deterministically; LLMs analyse.** Agents don't call tools through LLM tool-calling: each node runs its tools in a fixed order and gives the LLM the evidence. This follows doc §1.3 (deterministic where possible), keeps runs reproducible and cheaper, and works the same with all four providers. LLM tool-calling can be added later for open-ended investigation.

---

## Pending

### Phase 2–5 gaps

- [ ] JavaScript rendering for client-side sites (Playwright), behind a setting
- [ ] Trend data source (no reliable free official API; currently reported as unavailable)
- [ ] Optional keyword-provider and competitor data (doc §20 B6–B7)
- [ ] Embeddings + semantic retrieval (ChromaDB embedded) to replace lexical page matching
- [ ] Human approval flow for recommendations (approve / reject, `recommendation_events`)
- [ ] Normalized tables for pages, findings, keyword metrics and recommendations (today stored as JSON per agent result)
- [ ] Scheduler for recurring runs (weekly crawl, daily Search Console) and a monthly report
- [ ] Alert delivery (email/Slack) and AI-answer visibility sampling (doc §11)

### Phase 6 — Production hardening

- [ ] Authentication beyond a single API key; per-tenant authorization
- [ ] Load and failure-injection tests (doc §13.5); agent evaluation benchmark (§13.3)
- [ ] Metrics (token cost, tool failure rates, durations) and dashboards
- [ ] Backup/restore procedure; deployment and rollback docs
- [ ] Outbound firewall for the crawler to close the DNS-rebinding window fully

---

## Open decisions

| Decision | Current state |
|---|---|
| LLM provider and model | All four supported; default `anthropic` / `claude-sonnet-5-5` / `medium`. |
| Embedding provider | Open — needed for Phase 4 semantic retrieval. |
| Target website | `machinoai.in` (default in `.env`). |
| Search Console access | **Chosen as the keyword data source.** Set up per README → Data sources; verify with `seo-agent --check-sources`. |
| Commercial keyword data allowed? | Unknown. |
| Deployment environment | Local by default; container optional; cloud target undecided. |
| Recommendation-only or approval-gated changes? | Recommendation-only. |

---

## Known issues

- The old `.venv` (Python 3.10) is kept but not used; the project's environment is `.venv312` (Python 3.12).
- Tests have only run against stand-in libraries in the build sandbox (no PyPI access there). `scripts/setup_env.sh` runs the full suite on the real packages; then try `seo-agent --max-pages 20`.
- Default model IDs and reasoning-level support come from provider docs as of Nov 2026; the provider API rejects a level the chosen model doesn't support.
- Without `PAGESPEED_API_KEY`, PageSpeed calls use a small anonymous quota and may be rate-limited (reported as a data gap).
- Crawler timings measure the crawler's network path, not real users; the report says so.
- Run commands from the project root so `.env` and `alembic.ini` are found.

---

## Change log

| Date | Change |
|---|---|
| 2026-10-28 | Project scaffolding: `pyproject.toml`, `.env` / `.env.example`, ignore files, `Dockerfile`, `docker-compose.yml`, Alembic config, folder layout, `README.md`. |
| 2026-10-28 | First Python modules drafted, then removed on request; re-added step by step. |
| 2026-10-30 | Added `docs/` and this progress tracker. |
| 2026-11-04 | LangChain LLM layer (OpenAI, Anthropic, Gemini, Inception) with global, per-agent and per-run switching. |
| 2026-11-05 | `.env` reorganized; `TARGET_SITE` (default `machinoai.in`); CLI runner. |
| 2026-11-05 | Agent prompts as versioned XML-tagged YAML; tool contract with time-partitioned output recording. |
| 2026-11-14 | Phase 1 finished and first end-to-end run: local SQLite storage (no Docker), migrations, LangGraph workflow with checkpoints and resume, four working agents, SSRF-safe HTTP client, crawler, technical rules, PageSpeed, Search Console, keyword scoring, content matching, Markdown report, FastAPI (`/runs`, health, API key), logging, prompts v2, 84 unit + API tests. Removed Postgres/Redis/Chroma services from the default setup. |
| 2026-11-14 | Estimated LLM cost per run: token usage per agent, price table with promo end dates, `LLM_PRICES` override, cost line on top of the report and per-agent costs in Run details, migration 0002; 105 unit tests. |
| 2026-11-14 | Reports made precise and actionable (action plan, coverage, template health, URL-level values, CSV exports), new technical checks, template-stratified crawl sampling, Search Console quick wins / cannibalization / declining pages, `--check-sources`; prompts v3 (seo_audit, keyword_research, performance_reporting); 99 unit tests. |
| 2026-11-14 | Python 3.12 environment: `.python-version`, `scripts/setup_env.sh` (create `.venv312`, install, test; old `.venv` kept), 3.12 classifiers; code audited for 3.12 compatibility; README and this tracker updated. |
