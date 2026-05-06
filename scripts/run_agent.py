#!/usr/bin/env -S /home/puneetha/Documents/IterativeResearch/VIKAS/.venv/bin/python
"""CLI to run any registered agent standalone.

Usage:
    python scripts/run_agent.py \\
        --agent keyword_research \\
        --params '{"seed_keyword": "ai marketing"}' \\
        --org 00000000-0000-0000-0000-000000000001

    uv run python scripts/run_agent.py --agent keyword_research \\
        --params '{"seed_keyword": "content strategy"}' \\
        --org <org_uuid>
"""
import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

# Put apps/api on the path
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "api"))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from core.agent_base import AgentContext
from core.agent_registry import get as get_agent
from core.cost_tracker import CostTracker
from core.llm_router import LLMRouter
from config.settings import settings
from db.session import org_session

from core.agent_registry import import_all_agents
import_all_agents()  # registers all 34 agents via @register decorators


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run a Vikas agent standalone")
    p.add_argument("--agent", required=True, help="Agent name (e.g. keyword_research)")
    p.add_argument(
        "--params",
        default="{}",
        help='Agent params as JSON string (e.g. \'{"seed_keyword": "ai marketing"}\')',
    )
    p.add_argument("--org", required=True, help="Organization UUID")
    p.add_argument("--run-id", default=None, help="Optional run UUID (generated if omitted)")
    return p


async def _run(agent_name: str, params: dict, org_id: str, run_id: str) -> dict:
    config_path = Path(__file__).parent.parent / "apps" / "api" / "config" / "model_tiers.yaml"
    router = LLMRouter(config_path, CostTracker(), settings)

    agent = get_agent(agent_name)

    async with org_session(org_id) as db:
        ctx = AgentContext(
            org_id=org_id,
            run_id=run_id,
            params=params,
            config={},
            db=db,
            llm=router,
        )
        result = await agent.run(ctx)

    return result.model_dump()


def main() -> None:
    args = _build_parser().parse_args()

    try:
        params = json.loads(args.params)
    except json.JSONDecodeError as exc:
        print(f"ERROR: --params is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    run_id = args.run_id or str(uuid.uuid4())

    print(f"Running agent: {args.agent}")
    print(f"  org_id : {args.org}")
    print(f"  run_id : {run_id}")
    print(f"  params : {json.dumps(params, indent=2)}")
    print()

    result = asyncio.run(_run(args.agent, params, args.org, run_id))

    print("Result:")
    print(json.dumps(result, indent=2, default=str))

    if result.get("status") != "success":
        sys.exit(1)


if __name__ == "__main__":
    main()
