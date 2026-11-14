"""Command-line runner for the SEO Agent (run from the project root so `.env` is found).

    python -m src.runner                          # analyse TARGET_SITE from .env
    python -m src.runner --site example.com       # another site, this run only
    python -m src.runner --max-pages 50           # quick, smaller crawl
    python -m src.runner --provider openai --reasoning high   # LLM for this run only
    python -m src.runner --check-llm              # verify API keys/models, then exit
    python -m src.runner --check-sources          # verify Search Console + PageSpeed
    python -m src.runner --resume <run_id>        # continue an interrupted run

After `pip install -e .` the same is available as the `seo-agent` command.
Everything runs locally: results go to data/output/, run history to data/seo_agent.db.
"""

import argparse
import asyncio
import sys
import uuid
from typing import Any

from src import __version__
from src.config import AgentName, LLMProvider, get_settings, normalize_site
from src.llm import LLMConfigurationError, LLMSpec, create_chat_model, resolve_llm_spec
from src.observability.logging import configure_logging
from src.orchestration.workflow import (
    PreparedRun,
    execute_workflow,
    load_run,
    prepare_run,
)
from src.persistence.database import dispose_engine, run_migrations
from src.prompts import AgentPrompt, load_prompt
from src.tools.base import ToolFailure
from src.tools.performance import PageSpeedRequest, analyze_page_speed
from src.tools.search_console import check_access

_PING_PROMPT = "Reply with exactly one word: OK"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="seo-agent", description="Run the SEO + AEO agent.")
    parser.add_argument("--site", help="domain to analyse (default: TARGET_SITE from .env)")
    parser.add_argument("--max-pages", type=int, help="crawl page budget for this run")
    parser.add_argument(
        "--provider", choices=[p.value for p in LLMProvider], help="LLM provider, this run only"
    )
    parser.add_argument("--model", help="LLM model for every agent, this run only")
    parser.add_argument(
        "--reasoning", help="default|none|low|medium|high or a provider-native value"
    )
    parser.add_argument(
        "--check-llm", action="store_true", help="send one tiny prompt per model, then exit"
    )
    parser.add_argument(
        "--check-sources",
        action="store_true",
        help="check Search Console access and the PageSpeed key, then exit",
    )
    parser.add_argument("--resume", metavar="RUN_ID", help="resume an interrupted run")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def _llm_overrides(args: argparse.Namespace) -> dict[str, str]:
    values = {"provider": args.provider, "model": args.model, "reasoning": args.reasoning}
    return {k: v for k, v in values.items() if v}


def _print_plan(
    run: PreparedRun, specs: dict[AgentName, LLMSpec], prompts: dict[AgentName, AgentPrompt]
) -> None:
    print(f"SEO Agent {__version__}")
    print(f"  site    : {run.site}")
    print(f"  run_id  : {run.run_id}")
    print(f"  outputs : {run.output_dir}/\n")
    print(f"  {'agent':<24}{'provider':<12}{'model':<22}{'reasoning':<11}prompt")
    for agent, spec in specs.items():
        print(
            f"  {agent.value:<24}{spec.provider.value:<12}{spec.model:<22}"
            f"{spec.reasoning:<11}{prompts[agent].ref}"
        )
    print()


def _print_summary(run: PreparedRun, final: dict[str, Any]) -> None:
    print("\nResult")
    for step, status in final.get("task_status", {}).items():
        print(f"  {step:<24}{status}")
    if final.get("pages_crawled") is not None:
        print(f"\n  pages crawled : {final['pages_crawled']}")
    cost = final.get("cost") or {}
    if cost.get("llm_calls"):
        print(f"  LLM cost      : ${cost['cost_usd']:.4f} estimated ({cost['llm_calls']} calls, "
              f"{cost['input_tokens']:,} in / {cost['output_tokens']:,} out tokens)")
    gaps = final.get("data_gaps", [])
    if gaps:
        print(f"  data gaps     : {len(gaps)} (listed in the report)")
    for error in final.get("errors", []):
        print(f"  error         : {error}")
    if final.get("report_path"):
        print(f"\n  report        : {final['report_path']}")
    print(f"  all outputs   : {run.output_dir}/")


def _check_llms(specs: dict[AgentName, LLMSpec]) -> bool:
    """Call each distinct model once. Returns True if all respond."""
    all_ok = True
    for spec in dict.fromkeys(specs.values()):
        label = f"{spec.provider.value}/{spec.model} (reasoning={spec.reasoning})"
        try:
            reply = create_chat_model(spec).invoke(_PING_PROMPT)
            print(f"  [ok]   {label}: {str(reply.content).strip()[:40]!r}")
        except Exception as exc:  # report every failure, don't stop at the first one
            all_ok = False
            print(f"  [fail] {label}: {type(exc).__name__}: {exc}")
    return all_ok


async def _check_sources(site: str) -> int:
    """Verify optional data sources: Search Console access and PageSpeed Insights."""
    settings = get_settings()
    ok = True

    print("Search Console")
    gsc = await check_access(site)
    if gsc.get("service_account"):
        print(f"  service account : {gsc['service_account']}")
    if gsc["status"] == "ok":
        print(f"  [ok]   will use property {gsc['will_use']}")
    elif gsc["status"] == "not_configured":
        print("  [skip] not configured: set GSC_SERVICE_ACCOUNT_FILE in .env (see README)")
    elif gsc["status"] == "no_access":
        ok = False
        print(f"  [fail] no access to {site}. Add the service account above as a user on the")
        print("         property (Search Console → Settings → Users and permissions).")
        for url, permission in gsc.get("properties", []):
            print(f"         can read: {url} ({permission})")
    else:
        ok = False
        print(f"  [fail] {gsc.get('detail')}")

    print("PageSpeed Insights")
    key_note = "with PAGESPEED_API_KEY" if settings.pagespeed_api_key else "anonymous (no key)"
    request = PageSpeedRequest(run_id=uuid.uuid4(), site=site, url=f"https://{site}/")
    try:
        # Call the unrecorded function: a diagnostic shouldn't create a run folder.
        output = await analyze_page_speed.__wrapped__(request)
        score = (output.data or {}).get("lab", {}).get("performance_score")
        print(f"  [ok]   {key_note}; homepage mobile performance score {score}")
    except ToolFailure as exc:
        ok = False
        print(f"  [fail] {key_note}: {exc.error.message}")
    return 0 if ok else 1


async def _run(args: argparse.Namespace, site: str, llm: dict[str, str]) -> int:
    try:
        if args.resume:
            run = await load_run(uuid.UUID(args.resume))
            llm = run.options.get("llm", {})
        else:
            run = await prepare_run(site, {"max_pages": args.max_pages, "llm": llm})
        specs = {agent: resolve_llm_spec(agent, **llm) for agent in AgentName}
        _print_plan(run, specs, {agent: load_prompt(agent) for agent in AgentName})
        print(f"Running… (interrupt with Ctrl+C; resume with --resume {run.run_id})\n")
        final = await execute_workflow(run, resume=bool(args.resume))
    finally:
        await dispose_engine()
    _print_summary(run, dict(final))
    return 1 if final.get("task_status", {}).get("validate_site") != "succeeded" else 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        settings = get_settings()
        site = normalize_site(args.site) if args.site else settings.target_site
        llm = _llm_overrides(args)
        specs = {agent: resolve_llm_spec(agent, **llm) for agent in AgentName}
        for agent in AgentName:
            load_prompt(agent)  # fail fast on an invalid prompt file
        if args.resume:
            uuid.UUID(args.resume)
    except (LLMConfigurationError, ValueError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    if args.check_llm:
        print("Checking LLM connections…")
        return 0 if _check_llms(specs) else 1
    if args.check_sources:
        return asyncio.run(_check_sources(site))

    configure_logging(settings.log_level, json_output=settings.log_json)
    if settings.auto_migrate and not run_migrations():
        print("alembic.ini not found: run from the project root.", file=sys.stderr)
        return 2

    try:
        return asyncio.run(_run(args, site, llm))
    except KeyboardInterrupt:
        print("\nInterrupted. Resume later with --resume <run_id> (shown above).")
        return 130


if __name__ == "__main__":
    sys.exit(main())
