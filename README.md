<div align="center">

# SEO Agent

**An autonomous SEO & AEO agent that crawls your site, measures what matters, and hands you a prioritized action plan — with the exact pages, the owner, and how to verify each fix.**

[![Python](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-workflow-1C3C3C?logo=langchain&logoColor=white)](https://docs.langchain.com/oss/python/langgraph/overview)
[![LangChain](https://img.shields.io/badge/LangChain-LLMs-1C3C3C?logo=langchain&logoColor=white)](https://python.langchain.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-local%20first-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![LLMs](https://img.shields.io/badge/LLMs-OpenAI%20%7C%20Anthropic%20%7C%20Gemini%20%7C%20Mercury-6E56CF)](#llm-providers)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-D7FF64?logo=ruff&logoColor=black)](https://docs.astral.sh/ruff/)

[Quick start](#quick-start) ·
[How it works](#how-it-works) ·
[What you get](#what-you-get) ·
[Configuration](#configuration) ·
[Architecture](docs/architecture.md) ·
[FAQ](#faq)

</div>

---

## Why SEO Agent?

Most SEO tools hand you a 400-row spreadsheet. SEO Agent hands you **the 10 things to do next**:

- **Measures before it reasons.** A real crawler, 33 rule-based checks, PageSpeed lab + real-user data and Search Console metrics produce the evidence. The LLM only prioritizes and explains it — it never invents numbers.
- **Actionable, not generic.** Every action names the URLs or page template, an owner (developer / content / SEO), effort, impact, and a `done when` check anyone can run.
- **Answer-engine ready (AEO).** Checks whether ChatGPT, Perplexity, Claude and Google crawlers can reach you, flags missing structured data per page type, and writes content briefs with direct-answer sections.
- **Runs on your laptop.** One command, SQLite files, no Docker or servers. Postgres is a one-line switch for production.
- **Bring your own LLM.** OpenAI, Anthropic, Gemini or Inception Mercury — per run or per agent — with the estimated cost of every run printed on the report.

```text
> Cost:     $0.0145 estimated LLM spend · 6 calls on gpt-6-luna · 70,000 input / 15,000 output tokens
> Coverage: 100 of 2,720 sitemap URLs fetched (3.7%): 98 HTML pages analysed, 2 returned errors ·
            PageSpeed: 5 of 5 priority pages measured · Search Console: connected (sc-domain:example.com)

## Action plan
| # | Priority | Action                                          | Pages / template | Owner     | Effort | Impact |
|---|----------|-------------------------------------------------|------------------|-----------|--------|--------|
| 1 | p1       | Fix the 503 on topic pages                      | /topic/*         | developer | medium | high   |
| 2 | p1       | Cache job listing pages at the edge (3 s → <1 s) | /jobs/*/*        | developer | medium | high   |
| 3 | p1       | Rewrite titles for 6 queries ranking 4–15       | /jobs, /models … | content   | small  | high   |
```
<sub>Illustrative excerpt of `report.md`.</sub>

---

## Quick start

> **Requirements:** Python 3.12 and an API key for one LLM provider. Nothing else.

```bash
# 1. Clone and configure
git clone <your-repo-url> seo_agent && cd seo_agent
cp .env.example .env              # set TARGET_SITE and e.g. OPENAI_API_KEY (top of the file)

# 2. Create the Python 3.12 environment, install, run the tests
bash scripts/setup_env.sh         # uses uv if available (downloads Python 3.12 for you)
source .venv312/bin/activate

# 3. Run
seo-agent --check-llm             # verify your key and model
seo-agent --max-pages 50          # quick first run on TARGET_SITE
```

The run prints a plan, live progress, and finally the path to your report:

```text
  report        : data/output/example.com/2026-11-14/run_81da868b-…/report.md
  LLM cost      : $0.0145 estimated (6 calls, 70,000 in / 15,000 out tokens)
```

<details>
<summary><b>No Python 3.12? / Manual install / PyCharm</b></summary>

- **Install Python 3.12:** `brew install uv` (recommended; the setup script then fetches Python itself) or `brew install python@3.12`.
- **Manual install:** `python3.12 -m venv .venv312 && .venv312/bin/pip install -e ".[dev]"`
- **PyCharm:** Settings → Python Interpreter → add `.venv312/bin/python`. Run configuration: *Python*, **module** `src.runner`, working directory = project root, parameters e.g. `--max-pages 20`.

</details>

---

## How it works

```mermaid
flowchart LR
    V["Validate site"] --> A["SEO audit"]
    A --> K["Keyword research"]
    K --> C["Content strategy"]
    C --> R["Performance report"]
    A -.->|no pages crawled| R
```

| Step | Tools (deterministic, every call recorded) | The LLM then… |
|---|---|---|
| **Validate site** | DNS (public IPs only), homepage fetch, redirect chain | – |
| **SEO audit** | robots.txt + sitemaps → template-stratified crawl → 33 technical rules → PageSpeed lab + CrUX field data | Prioritizes findings, adds expected-schema checks per page type, assigns owner, effort, `done when` |
| **Keyword research** | Search Console queries × pages (28 days vs the 28 before) → versioned opportunity score, quick wins, cannibalization, declining pages; site topics | Picks ≤ 25 opportunities and the exact change on each target page |
| **Content strategy** | Topic-to-page matching over the crawled inventory | Writes ≤ 10 briefs: update vs create, outline, questions, internal links, schema |
| **Performance report** | Report renderer + CSV exports | Builds the 5–12 item action plan, executive summary and alerts |

Every step is isolated: if one fails, it is marked failed and the run continues. State is checkpointed after each step, so `seo-agent --resume <run_id>` picks up where an interrupted run stopped.

**Deep dive:** [`docs/architecture.md`](docs/architecture.md) — system diagram, agent sequence, retry policy, logging events, data model, every threshold and formula.

---

## What you get

Each run writes a self-contained folder: `data/output/<site>/<YYYY-MM-DD>/run_<run_id>/`

| File | Contents |
|---|---|
| **`report.md`** | Cost and coverage on top, executive summary, **prioritized action plan**, alerts, template health, technical findings with measured values per URL, keyword opportunities, pages competing for the same query, content recommendations, data gaps, per-agent tokens and cost |
| `action_plan.csv` | The action plan as a task list — import into Jira, Linear or Sheets |
| `findings.csv` | One row per affected URL per issue, with the measured value and the fix |
| `pages.csv` | Page inventory: status, response time, title, description, H1, words, schema |
| `*_agent_*.json` | Full agent outputs, e.g. content briefs with outlines and internal links |
| `*_<tool>_*.json`, `manifest.jsonl` | Raw evidence from every tool call, time-stamped |
| `run.log` | This run's structured log: steps, tool calls, retries, failed pages, LLM calls, cost |

Run history lives in `data/seo_agent.db`; the next run compares itself with the previous one.

---

## Usage

### Command line

```bash
seo-agent                                        # full run on TARGET_SITE
seo-agent --site example.com --max-pages 100     # another site / page budget, this run only
seo-agent --provider anthropic --reasoning high  # another LLM, this run only
seo-agent --check-llm                            # one tiny call per configured model
seo-agent --check-sources                        # Search Console access + PageSpeed status
seo-agent --resume <run_id>                      # continue an interrupted run
```

`python -m src.runner …` works the same. Run from the project root so `.env` is found.

### HTTP API

```bash
uvicorn src.main:app --reload                    # docs at http://localhost:8000/docs

curl -X POST localhost:8000/runs \
  -H 'content-type: application/json' \
  -d '{"site": "example.com", "max_pages": 50}'  # → 202 {"run_id": "…"}

curl localhost:8000/runs/<run_id>                # status, per-agent results, report path, cost
```

Set `API_KEY` in `.env` to require an `X-API-Key` header. Health checks: `/health/live`, `/health/ready`.

---

## Configuration

Everything lives in **`.env`** (copy of `.env.example`); blank values use safe defaults.

| Setting | Default | What it does |
|---|---|---|
| `TARGET_SITE` | `machinoai.in` | Domain to analyse (a full URL also works) |
| `LLM_PROVIDER` / `LLM_MODEL` / `LLM_REASONING` | `anthropic` / provider default / `medium` | Which LLM runs every agent |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `INCEPTION_API_KEY` | – | Only the selected provider needs a key |
| `CRAWLER_MAX_PAGES` | `500` | Page budget per run (`--max-pages` overrides) |
| `HTTP_MAX_ATTEMPTS` / `LLM_MAX_RETRIES` | `2` / `1` | At most 2 tries per request, then record and move on |
| `PAGESPEED_API_KEY` | – | Optional; raises the PageSpeed quota |
| `GSC_SERVICE_ACCOUNT_FILE` | – | Optional; enables measured keyword research |
| `DATABASE_URL` | `sqlite+aiosqlite:///data/seo_agent.db` | Postgres for production |
| `LOG_LEVEL` / `LOG_JSON` / `LOG_FILE` | `INFO` / `false` / `data/logs/seo_agent.log` | Logging |

Full list: [`docs/architecture.md#11-configuration`](docs/architecture.md#11-configuration-srcconfigpy-env).

### LLM providers

| Provider | `LLM_PROVIDER` | Default model | Key |
|---|---|---|---|
| OpenAI | `openai` | `gpt-5.5` | `OPENAI_API_KEY` |
| Anthropic | `anthropic` | `claude-sonnet-5-5` | `ANTHROPIC_API_KEY` |
| Google Gemini | `gemini` | `gemini-3.8-flash` | `GOOGLE_API_KEY` |
| Inception (Mercury) | `inception` | `mercury-3` | `INCEPTION_API_KEY` |

`LLM_REASONING` accepts `default · none · low · medium · high` (mapped per provider) or provider-native values like `xhigh` and `max`. Mix and match per agent, e.g. a cheap model for the audit and a stronger one for content briefs:

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=gpt-6-luna
CONTENT_STRATEGY_LLM_MODEL=gpt-6.1-sol
CONTENT_STRATEGY_LLM_REASONING=high
```

<details>
<summary><b>Set up Search Console (recommended — turns keyword guesses into measured data)</b></summary>

1. Google Cloud console → enable **Google Search Console API**.
2. IAM & Admin → Service Accounts → create one (no roles) → Keys → Add key → **JSON**.
3. Save it as `secrets/gsc-service-account.json` (git-ignored) and set `GSC_SERVICE_ACCOUNT_FILE` to its full path.
4. Search Console → your property → Settings → Users and permissions → **Add user** → the service account's email, permission *Restricted*.
5. Verify: `seo-agent --check-sources` shows the account email and which property will be used.

</details>

<details>
<summary><b>Set up PageSpeed Insights</b></summary>

Google Cloud console → enable **PageSpeed Insights API** → Credentials → **Create API key** → set `PAGESPEED_API_KEY`. Without a key the anonymous quota is small and some measurements may be skipped (listed as data gaps).

</details>

---

## Reliability & observability

- **Retry policy:** every request — pages, PageSpeed, Search Console, LLM — gets **at most 2 tries** (temporary errors only, honouring `Retry-After`). A page that still fails is recorded and the crawl moves on. → [details](docs/architecture.md#6-retry-policy)
- **Structured logging:** console, a rotating JSON log at `data/logs/seo_agent.log`, and a per-run `run.log`. Run, site and step on every line; API keys redacted; URLs logged without query strings. → [event catalogue](docs/architecture.md#7-logging)
- **Safe by default:** public-IP-only DNS, re-validated redirects, crawl scope allow-list, response size and time limits, robots.txt respected.
- **Resumable:** checkpoints after every step; Ctrl+C is safe.
- **Traceable:** every number in the report comes from a recorded tool call in the run folder.

---

## Project structure

<details>
<summary><b>Show the tree</b></summary>

```text
seo_agent/
├── .env / .env.example     # all keys & config (only .env.example is committed)
├── .python-version         # 3.12
├── pyproject.toml          # dependencies, `seo-agent` command, ruff / mypy / pytest config
├── scripts/setup_env.sh    # create .venv312, install, run tests
├── alembic.ini, migrations/  # database schema (applied automatically when AUTO_MIGRATE=true)
├── Dockerfile, docker-compose.yml  # optional container setup
├── src/                    # the application package: `from src.<module> import …`
│   ├── runner.py           # CLI entry point (`seo-agent`)
│   ├── main.py             # FastAPI app
│   ├── config.py           # typed settings — the only place env vars are read
│   ├── api/                # HTTP routes and schemas
│   ├── orchestration/      # LangGraph state, graph, checkpoints, run lifecycle
│   ├── agents/             # the four agents (tools → evidence → LLM → validated JSON)
│   ├── tools/              # crawler, technical checks, PageSpeed, Search Console, scoring, report
│   ├── llm/                # provider-agnostic chat models + price table
│   ├── prompts/            # one <agent>.yaml per agent (versioned, XML-tagged) + shared.yaml
│   ├── persistence/        # SQLite/Postgres models, repositories, run-folder writer
│   └── observability/      # structured logging
├── tests/unit/, tests/integration/
├── data/                   # local database, checkpoints, logs and run outputs (git-ignored)
└── docs/architecture.md    # architecture diagrams and how a run works
```

</details>

---

## Production

```bash
pip install -e ".[postgres]"
export DATABASE_URL=postgresql+psycopg://user:pass@host:5432/seo_agent
alembic upgrade head                 # as a deploy step; set AUTO_MIGRATE=false
LOG_JSON=true API_KEY=… uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Inject secrets from a secret manager instead of `.env`. A `Dockerfile` (non-root, health check) and an optional `docker-compose.yml` (API on localhost, optional Postgres profile) are included.

---

## Development

```bash
pytest -q                       # unit + API tests (no network, no LLM calls)
ruff check . && ruff format .
mypy src
```

<details>
<summary><b>Conventions</b></summary>

- **Secrets:** only in `.env` or a secret manager; read via `get_settings()`; never hard-coded, logged or sent to an LLM.
- **Tools:** take a `ToolRequest`, return a `ToolOutput`, decorated with `@recorded_tool("name")`; network access only through `tools/http.py`.
- **Agents** run tools and analyse evidence; they never call external services directly.
- **Prompts** live only in `src/prompts/*.yaml`: well-formed XML, every `${placeholder}` declared, `version` bumped on each change.
- **Schema changes:** `alembic revision --autogenerate -m "…"`.
- **Docs:** when behaviour changes, update the matching section of `docs/architecture.md`.

</details>

---

## Roadmap

- [ ] JavaScript rendering (Playwright) for client-side-rendered pages
- [ ] Trend data source, keyword-provider data and competitor analysis
- [ ] Semantic page matching with embeddings (ChromaDB, embedded)
- [ ] Approval workflow for recommendations
- [ ] Scheduler for recurring runs, monthly report and alert delivery
- [ ] AI-answer visibility sampling (are you cited by answer engines?)

---

## FAQ

<details>
<summary><b>Do I need Docker, Postgres or Redis?</b></summary>

No. Everything runs locally with SQLite files in `data/`. Docker and Postgres are optional for production.
</details>

<details>
<summary><b>Do I need Search Console?</b></summary>

No, but without it keyword research is based on your own page topics and marked as unmeasured. With it you get real queries, quick wins, cannibalization and declining pages.
</details>

<details>
<summary><b>How much does a run cost?</b></summary>

Crawling, PageSpeed and Search Console are free. The LLM cost depends on the model and page budget; every report shows the estimated total at the top and per agent in Run details. Prices are in `src/llm/pricing.py` and can be overridden with `LLM_PRICES`.
</details>

<details>
<summary><b>Will it change my website?</b></summary>

No. It only reads public pages and APIs (read-only Search Console scope) and writes recommendations.
</details>

<details>
<summary><b>A run was interrupted. Do I start again?</b></summary>

No: `seo-agent --resume <run_id>` continues from the last completed step. The run id is printed at the start of every run.
</details>

---

<div align="center">

**Design:** [`seo_aeo_growth_agent_design.md`](seo_aeo_growth_agent_design.md) · **Architecture:** [`docs/architecture.md`](docs/architecture.md)

</div>
