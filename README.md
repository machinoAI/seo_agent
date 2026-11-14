# SEO Agent

Autonomous SEO + AEO growth agent: crawls a site, audits it, finds keyword and content
opportunities and writes a report. Python · LangGraph · LangChain · FastAPI · SQLite.
Runs entirely on your machine — no Docker, database server or Redis needed.

Design: [`seo_aeo_growth_agent_design.md`](seo_aeo_growth_agent_design.md) ·
Status and what's pending: [`docs/progress.md`](docs/progress.md)

## Quick start

```bash
# 1. Configure: TARGET_SITE and the API key of your LLM provider (top of .env)
cp .env.example .env            # skip if .env already exists

# 2. Create the Python 3.12 environment, install, and run the tests (one command)
bash scripts/setup_env.sh
source .venv312/bin/activate

# 3. Run
seo-agent --check-llm           # verify your LLM key and model
seo-agent --max-pages 50        # quick first run on TARGET_SITE
seo-agent                       # full run (CRAWLER_MAX_PAGES)
```

**Python 3.12** is required (pinned in `.python-version`). `scripts/setup_env.sh` uses
[uv](https://docs.astral.sh/uv/) if installed — it downloads Python 3.12 automatically —
otherwise `python3.12`. It creates `.venv312` and leaves any other environment (e.g. an
old `.venv`) untouched. Without
either, install one first: `brew install uv` (recommended) or `brew install python@3.12`.
Manual equivalent: `python3.12 -m venv .venv312 && .venv312/bin/pip install -e ".[dev]"`.
In PyCharm / VS Code, select `.venv312/bin/python` as the project interpreter.
PyCharm run configuration: *+ → Python*, interpreter `.venv312` (Python 3.12), **module**
`src.runner`, working directory = project root (so `.env` is found), script parameters
e.g. `--max-pages 20`, `--check-llm` or `--reasoning high`.

Each run prints its `run_id` and writes everything to
`data/output/<site>/<YYYY-MM-DD>/run_<run_id>/`. Run history is kept in `data/seo_agent.db`.

| File | What it's for |
|---|---|
| **`report.md`** | **Estimated LLM cost** (total on top, per agent in Run details), coverage line, executive summary, **prioritized action plan** (priority, pages/template, owner, effort, impact, why, done-when), alerts, template health, technical findings with measured values per URL, keyword opportunities (+ pages competing for the same query), content recommendations, data gaps |
| `action_plan.csv` | The action plan as a task list (import into Jira/Sheets) |
| `findings.csv` | One row per affected URL per issue, with the measured value and fix |
| `pages.csv` | Page inventory: status, response time, title, description, H1, words, schema |
| `*_agent_*.json` | Full agent outputs, e.g. content briefs with outlines and internal links |
| `*_<tool>_*.json`, `manifest.jsonl` | Raw evidence from every tool call |

The crawl samples pages evenly across URL templates (e.g. `/jobs/*/*`, `/concepts/*/*`),
so even `--max-pages 50` covers hubs and detail pages of every section.

More options:

```bash
seo-agent --site example.com                      # another site, this run only
seo-agent --provider openai --reasoning high      # another LLM, this run only
seo-agent --check-sources                         # verify Search Console + PageSpeed access
seo-agent --resume <run_id>                       # continue an interrupted run
```

### Data sources

The run works without them and lists them as data gaps, but keyword research needs
Search Console to be measured instead of estimated.

- **PageSpeed** (`PAGESPEED_API_KEY`): Google Cloud console → enable *PageSpeed Insights API* → Credentials → API key.
- **Search Console** (`GSC_SERVICE_ACCOUNT_FILE`, optional `GSC_PROPERTY`):
  1. Google Cloud console → enable *Google Search Console API*.
  2. IAM & Admin → Service Accounts → create one (no roles) → Keys → Add key → JSON.
  3. Save the file as `secrets/gsc-service-account.json` (git-ignored) and set
     `GSC_SERVICE_ACCOUNT_FILE` to its full path.
  4. Search Console → your property → Settings → Users and permissions → Add user →
     the service account's email, permission *Restricted* (read-only).
  5. `seo-agent --check-sources` shows the account email and which property will be used.

  The agent then reads queries × pages for the last 28 days (and the 28 before) and
  derives quick wins (positions 4–15), cannibalization, declining pages and scores.

## API

```bash
uvicorn src.main:app --reload               # http://localhost:8000/docs
curl -X POST localhost:8000/runs -H 'content-type: application/json' -d '{"site": "machinoai.in", "max_pages": 50}'
curl localhost:8000/runs/<run_id>
```

Set `API_KEY` in `.env` to require an `X-API-Key` header. Health: `/health/live`, `/health/ready`.

## How a run works

```
validate_site → seo_audit → keyword_research → content_strategy → performance_reporting
                   │ (no pages crawled) ────────────────────────────────┘
```

Each agent runs its tools first (deterministic, every call recorded), then its LLM
analyses that evidence using the agent's prompt in `prompts/<agent>.yaml` and returns
validated JSON. Failures are isolated: a failed step is reported and the run continues.
Checkpoints (`data/checkpoints.db`) make interrupted runs resumable.

## LLM providers

`openai`, `anthropic`, `gemini`, `inception` (Mercury), via LangChain. Set `LLM_PROVIDER`,
`LLM_MODEL` (blank = provider default) and `LLM_REASONING` (`default | none | low | medium
| high`, or a provider-native value). Override per agent with `<AGENT>_LLM_*` or per run
with the runner flags. Details: [`docs/progress.md`](docs/progress.md#llm-layer-how-switching-works).

## Layout

```text
seo_agent/
├── .env / .env.example     # all keys & config (only .env.example is committed)
├── .python-version         # 3.12 — used by uv / pyenv
├── pyproject.toml          # dependencies, `seo-agent` command, ruff / mypy / pytest config
├── scripts/setup_env.sh    # create the Python 3.12 .venv312, install, run tests
├── alembic.ini, migrations/  # database schema (applied automatically when AUTO_MIGRATE=true)
├── Dockerfile, docker-compose.yml  # optional container setup
├── src/                    # the application package: imports are `from src.<module> import …`
│   ├── runner.py           # CLI entry point (python -m src.runner, or `seo-agent`)
│   ├── main.py             # FastAPI app
│   ├── config.py           # typed settings — the only place env vars are read
│   ├── api/                # HTTP routes and schemas
│   ├── orchestration/      # LangGraph state, graph, checkpoints, run lifecycle
│   ├── agents/             # the four agents (tools → evidence → LLM → validated JSON)
│   ├── tools/              # crawler, technical checks, PageSpeed, Search Console, scoring…
│   ├── llm/                # provider-agnostic chat models
│   ├── prompts/            # one <agent>.yaml per agent (versioned, XML-tagged) + shared.yaml
│   ├── persistence/        # SQLite/Postgres models, repositories, output files
│   └── observability/      # structured logging
├── tests/unit/, tests/integration/
├── data/                   # local database, checkpoints and run outputs (git-ignored)
└── docs/progress.md        # development tracker
```

## Production

Set `DATABASE_URL=postgresql+psycopg://...`, install `pip install -e ".[postgres]"`, run
`alembic upgrade head` as a deploy step with `AUTO_MIGRATE=false`, set `LOG_JSON=true`
and `API_KEY`, and inject secrets from a secret manager instead of `.env`.

## Conventions

- **Secrets:** only in `.env` (local) or a secret manager. Read via `get_settings()`; never hard-code, log, or send to an LLM.
- **Tools:** take a `ToolRequest`, return a `ToolOutput`, decorated with `@recorded_tool("name")`; network access only through `tools/http.py` (SSRF-safe).
- **Agents** run tools and analyse evidence; they never call external services directly.
- **Prompts:** only in `prompts/*.yaml`; keep them well-formed XML, declare every `${placeholder}`, bump `version` on each change.
- **Schema changes:** `alembic revision --autogenerate -m "..."`.
- **Progress:** update `docs/progress.md` with every change.

## Dev commands

```bash
pytest                          # unit + integration tests
ruff check . && ruff format .
mypy src
```
