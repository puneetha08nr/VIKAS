#!/usr/bin/env python3
"""
Vikas eval runner — structural, relevance, ground-truth, and reporting.

Usage:
  python tests/evals/eval_runner.py structural [--agents keyword_research,gap_analyzer]
  python tests/evals/eval_runner.py relevance  [--agents keyword_research]
  python tests/evals/eval_runner.py ground-truth --agent keyword_research
  python tests/evals/eval_runner.py report [--days 30]

structural   runs pytest on TestStructural_* classes; logs pass/fail to evals_log
relevance    runs agent live → LLM judge → logs score to evals_log
ground-truth interactive monthly spot-check; prompts for human score
report       queries evals_log and prints a markdown trend table
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

# ── Path bootstrap ─────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "apps" / "api"))
sys.path.insert(0, str(_HERE))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from base import GroundTruthResult, RelevanceResult, judge_relevance, log_eval_result
from config.settings import settings

# ── Agent → eval module registry ──────────────────────────────────────────────
AGENT_EVAL_MODULES: dict[str, str] = {
    "keyword_research":   "seo.eval_keyword_research",
    "keyword_validator":  "seo.eval_keyword_validator",
    "gap_analyzer":       "seo.eval_gap_analyzer",
    "rank_tracker":       "seo.eval_rank_tracker",
    "article_planner":    "content.eval_article_planner",
    "article_writer":     "content.eval_article_writer",
    "content_director":   "content.eval_content_director",
    "linkedin_agent":     "content.eval_linkedin_agent",
    "document_ingester":  "knowledge.eval_document_ingester",
    "brand_voice_keeper": "knowledge.eval_brand_voice_keeper",
    "rag_searcher":       "knowledge.eval_rag_searcher",
    "wordpress_publisher":"knowledge.eval_wordpress_publisher",
}

_EVAL_ORG_ID = os.getenv("EVAL_ORG_ID", "00000000-0000-0000-0000-000000000001")


def _load_module(agent_name: str):
    path = AGENT_EVAL_MODULES.get(agent_name)
    if not path:
        raise ValueError(f"No eval module for agent {agent_name!r}")
    return importlib.import_module(path)


def _make_engine():
    return create_async_engine(settings.database_url, pool_pre_ping=True)


# ══════════════════════════════════════════════════════════════════════════════
# structural
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_structural(agents: list[str] | None) -> int:
    """
    Delegate to pytest for TestStructural_* classes, capture results per-agent,
    log a summary row to evals_log for each built agent.
    """
    import tempfile, xml.etree.ElementTree as ET

    target_agents = agents or list(AGENT_EVAL_MODULES.keys())
    junit_file = Path(tempfile.mktemp(suffix=".xml"))

    pytest_cmd = [
        sys.executable, "-m", "pytest", str(_HERE),
        "-k", "Structural",
        f"--junit-xml={junit_file}",
        "--tb=short", "-q", "--no-header",
    ]
    if agents:
        k_expr = " or ".join(f"Structural_{a}" for a in agents)
        pytest_cmd += ["-k", k_expr]

    proc = subprocess.run(pytest_cmd, capture_output=True, text=True, cwd=str(_REPO_ROOT))
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)

    # Parse JUnit XML for per-agent results
    per_agent_passed: dict[str, bool] = {}
    if junit_file.exists():
        tree = ET.parse(junit_file)
        for tc in tree.findall(".//testcase"):
            cls = tc.get("classname", "")
            failed = tc.find("failure") is not None or tc.find("error") is not None
            skipped = tc.find("skipped") is not None
            for name in AGENT_EVAL_MODULES:
                if f"Structural_{name}" in cls:
                    if not skipped:
                        prev = per_agent_passed.get(name, True)
                        per_agent_passed[name] = prev and not failed
        junit_file.unlink(missing_ok=True)

    # Log to DB
    engine = _make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        for agent in target_agents:
            mod = _load_module(agent)
            if not getattr(mod, "IS_BUILT", False):
                continue
            passed = per_agent_passed.get(agent, proc.returncode == 0)
            await log_eval_result(db, {
                "id": str(uuid.uuid4()),
                "org_id": None,
                "agent_name": agent,
                "eval_type": "structural",
                "score": 1.0 if passed else 0.0,
                "threshold": 1.0,
                "passed": passed,
                "inputs": None,
                "outputs": json.dumps({"pytest_returncode": proc.returncode}),
                "notes": f"pytest structural run — {datetime.now(timezone.utc).date()}",
            })
    await engine.dispose()

    print(f"\nStructural run complete — exit code {proc.returncode}")
    return proc.returncode


# ══════════════════════════════════════════════════════════════════════════════
# relevance
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_relevance(agents: list[str] | None) -> None:
    """
    For each built agent: run it via scripts/run_agent.py with sample inputs,
    judge the output with an LLM, log results to evals_log.
    """
    target_agents = agents or [
        a for a, m in AGENT_EVAL_MODULES.items()
        if getattr(_load_module(a), "IS_BUILT", False)
    ]

    engine = _make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    print(f"\nRunning relevance evals for: {', '.join(target_agents)}\n")

    async with Session() as db:
        for agent_name in target_agents:
            mod = _load_module(agent_name)
            if not getattr(mod, "IS_BUILT", False):
                print(f"  {agent_name}: SKIP (not built)")
                continue

            threshold: float = getattr(mod, "RELEVANCE_THRESHOLD", 0.70)
            sample_inputs: list[dict] = getattr(mod, "RELEVANCE_SAMPLE_INPUTS", [])
            criteria: str = getattr(mod, "RELEVANCE_JUDGE_CRITERIA", "")

            if not sample_inputs:
                print(f"  {agent_name}: SKIP (no sample inputs defined)")
                continue

            print(f"  {agent_name} (threshold={threshold})")
            for sample in sample_inputs[:2]:
                result_data = _run_agent_cli(agent_name, sample)
                if result_data is None:
                    print(f"    [{sample}] CLI run failed — skipping judge")
                    continue

                score, reasoning = await judge_relevance(
                    agent_name=agent_name,
                    inputs=sample,
                    outputs=result_data,
                    criteria=criteria,
                )
                passed = score >= threshold
                tag = "✅ PASS" if passed else "❌ FAIL"
                print(f"    score={score:.2f}  {tag}  — {reasoning[:80]}")

                rel = RelevanceResult(
                    agent_name=agent_name,
                    score=score,
                    threshold=threshold,
                    passed=passed,
                    inputs=sample,
                    outputs=result_data,
                    reasoning=reasoning,
                )
                await log_eval_result(db, rel.to_log_row())

    await engine.dispose()
    print("\nRelevance evals complete.")


def _run_agent_cli(agent_name: str, params: dict) -> dict | None:
    """
    Run an agent via scripts/run_agent.py, capture the result JSON.
    Returns the data dict from AgentResult, or None on failure.
    """
    cmd = [
        sys.executable,
        str(_REPO_ROOT / "scripts" / "run_agent.py"),
        "--agent", agent_name,
        "--params", json.dumps(params),
        "--org", _EVAL_ORG_ID,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(_REPO_ROOT), timeout=300)
    if proc.returncode != 0:
        return None
    # run_agent.py prints "Result:\n{json}"
    if "Result:" not in proc.stdout:
        return None
    try:
        raw = proc.stdout.split("Result:")[-1].strip()
        return json.loads(raw)
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# ground-truth
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_ground_truth(agent_name: str) -> None:
    """
    Interactive monthly spot-check. Shows each sample, runs the agent,
    prompts the human for a score (1-5), and logs to evals_log.
    """
    mod = _load_module(agent_name)
    if not getattr(mod, "IS_BUILT", False):
        print(f"Agent {agent_name!r} is not built yet — nothing to evaluate.")
        return

    samples = getattr(mod, "GROUND_TRUTH_SAMPLES", [])
    if not samples:
        print(f"No GROUND_TRUTH_SAMPLES defined for {agent_name}.")
        return

    print(f"\n{'='*60}")
    print(f"Ground Truth Spot Check — {agent_name}")
    print(f"{'='*60}")
    print(f"{len(samples)} samples  |  score 1 (terrible) → 5 (excellent)\n")

    engine = _make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with Session() as db:
        for idx, sample in enumerate(samples, 1):
            print(f"\n--- Sample {idx}/{len(samples)}: {sample.description} ---")
            print(f"Input:    {json.dumps(sample.input_params)}")
            print(f"Expected: {json.dumps(sample.expected_fields, indent=2)}")
            if sample.notes:
                print(f"Notes:    {sample.notes}")

            print("\n[Running agent...] ", end="", flush=True)
            actual = _run_agent_cli(agent_name, sample.input_params)
            if actual is None:
                print("FAILED — agent returned an error")
                actual = {}
            else:
                print("done")
            print(f"Actual output: {json.dumps(actual, indent=2)}")

            while True:
                try:
                    raw_score = input("\nYour score (1-5, or s to skip): ").strip()
                    if raw_score.lower() == "s":
                        print("  Skipped.")
                        break
                    score_int = int(raw_score)
                    if 1 <= score_int <= 5:
                        notes = input("Notes (optional, press Enter to skip): ").strip()
                        result = GroundTruthResult(
                            agent_name=agent_name,
                            sample_index=idx,
                            description=sample.description,
                            input_params=sample.input_params,
                            actual_outputs=actual,
                            human_score=score_int,
                            notes=notes,
                        )
                        await log_eval_result(db, result.to_log_row())
                        print(f"  Logged score={score_int}/5")
                        break
                    print("  Please enter a number between 1 and 5.")
                except (ValueError, EOFError):
                    print("  Invalid input — skipping.")
                    break

    await engine.dispose()
    print(f"\nGround truth session complete for {agent_name}.")


# ══════════════════════════════════════════════════════════════════════════════
# report
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_report(days: int) -> None:
    """
    Query evals_log for the past N days and print a markdown trend report.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    engine = _make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with Session() as db:
        rows = (await db.execute(
            text(
                "SELECT agent_name, eval_type, score, threshold, passed, run_at "
                "FROM evals_log "
                "WHERE run_at >= :since "
                "ORDER BY agent_name, eval_type, run_at"
            ),
            {"since": since},
        )).fetchall()

    await engine.dispose()

    # Group by agent
    from collections import defaultdict
    data: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        data[row.agent_name][row.eval_type].append(row)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"\n# Vikas Agent Eval Report — {now} (last {days} days)\n")
    print(
        f"| {'Agent':<22} | {'Structural':<14} | {'Relevance':<20} | {'Trend':<12} | {'Ground Truth':<14} |"
    )
    print(
        f"|{'-'*24}|{'-'*16}|{'-'*22}|{'-'*14}|{'-'*16}|"
    )

    for agent in sorted(AGENT_EVAL_MODULES):
        a_data = data.get(agent, {})

        # Structural — last run
        struct_rows = a_data.get("structural", [])
        if struct_rows:
            last_struct = struct_rows[-1]
            struct_col = "✅ PASS" if last_struct.passed else "❌ FAIL"
        else:
            struct_col = "— no data"

        # Relevance — last score + trend
        rel_rows = a_data.get("relevance", [])
        if rel_rows:
            last_score = rel_rows[-1].score
            threshold = rel_rows[-1].threshold
            pass_tag = "✅" if last_score >= threshold else "❌"
            rel_col = f"{last_score:.2f}/{threshold:.2f} {pass_tag}"
            trend_col = _trend(rel_rows)
        else:
            rel_col = "— no data"
            trend_col = "—"

        # Ground truth — average score
        gt_rows = a_data.get("ground_truth", [])
        if gt_rows:
            avg = sum(r.score * 5 for r in gt_rows) / len(gt_rows)
            gt_col = f"{avg:.1f}/5 ({len(gt_rows)} ratings)"
        else:
            gt_col = "— no data"

        print(
            f"| {agent:<22} | {struct_col:<14} | {rel_col:<20} | {trend_col:<12} | {gt_col:<14} |"
        )

    print()


def _trend(rows: list) -> str:
    """Compare earliest vs latest relevance score. Returns improving/degrading/stable."""
    if len(rows) < 2:
        return "—"
    oldest = rows[0].score
    newest = rows[-1].score
    delta = newest - oldest
    if delta > 0.05:
        return "📈 improving"
    if delta < -0.05:
        return "📉 degrading"
    return "➡ stable"


# ══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ══════════════════════════════════════════════════════════════════════════════

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Vikas eval runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_struct = sub.add_parser("structural", help="Run CI structural evals")
    p_struct.add_argument("--agents", help="Comma-separated agent names (default: all)")

    p_rel = sub.add_parser("relevance", help="Run weekly LLM-as-judge relevance evals")
    p_rel.add_argument("--agents", help="Comma-separated agent names (default: all built)")

    p_gt = sub.add_parser("ground-truth", help="Interactive monthly spot-check")
    p_gt.add_argument("--agent", required=True, help="Agent to spot-check")

    p_rep = sub.add_parser("report", help="Print trend report from evals_log")
    p_rep.add_argument("--days", type=int, default=30, help="Look-back window in days")

    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.command == "structural":
        agents = [a.strip() for a in args.agents.split(",")] if args.agents else None
        exit_code = asyncio.run(cmd_structural(agents))
        sys.exit(exit_code)

    elif args.command == "relevance":
        agents = [a.strip() for a in args.agents.split(",")] if args.agents else None
        asyncio.run(cmd_relevance(agents))

    elif args.command == "ground-truth":
        asyncio.run(cmd_ground_truth(args.agent))

    elif args.command == "report":
        asyncio.run(cmd_report(args.days))


if __name__ == "__main__":
    main()
