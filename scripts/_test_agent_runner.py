#!/usr/bin/env python3
"""
_test_agent_runner.py — VIKAS agent test harness engine.

Called by scripts/test_agent.sh. Reads tests/agent_configs/{agent}.yaml and runs:
  Pre-flight  : registry check, table exists
  A1          : unit tests pass
  A3          : RLS isolation — org B sees 0 rows
  A6          : concurrent run safety — no deadlock, 2 agent_runs written
  A7          : agent_runs logging accuracy
  B3          : API auth enforcement (or bypass documented)
  B4          : empty/default state shape correct (no null where [] expected)
  B5          : invalid input returns 4xx with detail field (no 500)

Writes: tests/agent_reports/{agent}_report.md
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import yaml

# ── Constants ──────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
DEV_ORG_ID = "00000000-0000-0000-0000-000000000001"
ISOLATION_ORG_ID = "99999999-9999-9999-9999-999999999999"
API_BASE = "http://localhost:8000/api/v1"
DB_DSN = "postgresql://vikas_app:vikas_app_dev@localhost:5432/vikas"


# ── Result dataclass ───────────────────────────────────────────────────────────
@dataclass
class CheckResult:
    check_id: str
    name: str
    status: str = "SKIP"       # PASS | FAIL | SKIP | WARN | ERROR
    detail: str = ""
    error: str = ""

    @property
    def icon(self) -> str:
        return {"PASS": "✅", "FAIL": "❌", "SKIP": "⬜", "WARN": "⚠️ ", "ERROR": "🔴"}.get(self.status, "?")


# ── Config loader ──────────────────────────────────────────────────────────────
def load_config(agent_name: str) -> dict:
    path = REPO_ROOT / "tests" / "agent_configs" / f"{agent_name}.yaml"
    if not path.exists():
        print(f"ERROR: Config not found: {path}")
        sys.exit(1)
    with open(path) as f:
        return yaml.safe_load(f)


def _env_flag(key: str) -> bool:
    """Read a boolean env var from .env file."""
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return False
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line.upper().startswith(f"{key.upper()}="):
            val = line.split("=", 1)[1].strip().strip("'\"").lower()
            return val in ("true", "1", "yes")
    return False


# ── Pre-flight checks ──────────────────────────────────────────────────────────
def preflight_registry(agent_name: str) -> CheckResult:
    r = CheckResult("P1", "Agent in registry")
    try:
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, 'apps/api'); "
             "from core.agent_registry import REGISTRY, import_all_agents; "
             f"import_all_agents(); print('FOUND' if '{agent_name}' in REGISTRY else 'NOT_FOUND')"],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        if "FOUND" in result.stdout:
            r.status = "PASS"
            r.detail = "Agent registered via @register decorator"
        else:
            r.status = "FAIL"
            r.detail = "Agent NOT in registry — add to import_all_agents() in core/agent_registry.py"
    except Exception as exc:
        r.status = "ERROR"
        r.error = str(exc)
    return r


def preflight_table(config: dict) -> CheckResult:
    table = config.get("output_table")
    r = CheckResult("P2", f"Output table exists ({table or 'n/a'})")
    if not table:
        r.status = "SKIP"
        r.detail = "Agent has no output table (orchestrator or read-only)"
        return r
    try:
        result = subprocess.run(
            ["docker", "exec", "vikas-db-1", "psql", "-U", "vikas", "-d", "vikas",
             "-tAc", f"SELECT EXISTS(SELECT FROM pg_tables WHERE schemaname='public' AND tablename='{table}')"],
            capture_output=True, text=True,
        )
        if "t" in result.stdout:
            r.status = "PASS"
            r.detail = f"Table public.{table} exists"
        else:
            r.status = "FAIL"
            r.detail = f"Table {table} NOT in DB — run: uv run alembic upgrade head"
    except Exception as exc:
        r.status = "ERROR"
        r.error = str(exc)
    return r


def preflight_unit_tests(agent_name: str) -> CheckResult:
    r = CheckResult("A1", "Unit tests pass")
    # Map agent name to test file
    dept_map = {
        "keyword_research": "seo", "keyword_validator": "seo", "opportunity_scorer": "seo",
        "trend_collector": "seo", "gap_analyzer": "seo", "rank_tracker": "seo",
        "site_auditor": "seo", "aeo_scanner": "seo", "topic_discovery": "seo",
        "article_planner": "content", "article_writer": "content", "content_director": "content",
        "lead_magnet_agent": "content", "linkedin_agent": "content", "newsletter_agent": "content",
        "twitter_agent": "content", "video_scriptwriter": "content",
        "competitor_monitor": "competitor", "content_extractor": "competitor",
        "keyword_overlap_analyzer": "competitor", "threat_assessor": "competitor",
        "competitor_discovery": "competitor",
        "brand_voice_keeper": "knowledge", "document_ingester": "knowledge",
        "internal_link_finder": "knowledge", "rag_searcher": "knowledge",
        "wordpress_publisher": "knowledge", "ai_assistant": "knowledge",
        "preference_learner": "ops",
        "pipeline_orchestrator": "orchestration", "auto_mode_engine": "orchestration",
        "strategy_synthesizer": "orchestration",
        "broll_selector": "video", "video_handoff": "video",
    }
    dept = dept_map.get(agent_name, "")
    test_path = REPO_ROOT / "tests" / "unit" / "agents" / dept / f"test_{agent_name}.py"
    if not test_path.exists():
        r.status = "SKIP"
        r.detail = f"Test file not found: {test_path.relative_to(REPO_ROOT)}"
        return r
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_path), "-q", "--tb=short",
             "--no-header", "-x"],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        if result.returncode == 0:
            lines = [l for l in result.stdout.splitlines() if l.strip()]
            summary = lines[-1] if lines else "passed"
            r.status = "PASS"
            r.detail = summary
        else:
            r.status = "FAIL"
            output = (result.stdout + result.stderr)[-800:]
            r.detail = output.replace("\n", " | ")
    except Exception as exc:
        r.status = "ERROR"
        r.error = str(exc)
    return r


# ── CLI runner helper ──────────────────────────────────────────────────────────
def _run_agent_cmd(agent_name: str, params: dict) -> list[str]:
    return [
        sys.executable, str(REPO_ROOT / "scripts" / "run_agent.py"),
        "--agent", agent_name,
        "--params", json.dumps(params),
        "--org", DEV_ORG_ID,
    ]


def _run_timeout(config: dict) -> int:
    """Agents that use an LLM get a longer timeout for the happy-path run."""
    return 180 if config.get("uses_llm", False) else 60


def run_agent_once(agent_name: str, params: dict, timeout: int = 60) -> tuple[bool, str]:
    """Returns (success, output_snippet)."""
    try:
        result = subprocess.run(
            _run_agent_cmd(agent_name, params),
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=timeout,
        )
        output = result.stdout[-500:] + result.stderr[-200:]
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, f"TIMEOUT after {timeout}s"
    except Exception as exc:
        return False, str(exc)


# ── A3: RLS isolation ──────────────────────────────────────────────────────────
async def check_rls(config: dict) -> CheckResult:
    r = CheckResult("A3", "RLS isolation (org B sees 0 rows)")
    table = config.get("output_table")
    if not table or not config.get("has_rls", True):
        r.status = "SKIP"
        r.detail = "No output table or RLS not applicable for this agent"
        return r
    try:
        conn = await asyncpg.connect(DB_DSN)
        try:
            await conn.execute(f"SET app.current_org_id = '{ISOLATION_ORG_ID}'")
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
            if count == 0:
                r.status = "PASS"
                r.detail = f"Org B sees 0 rows in {table} — RLS enforced"
            else:
                r.status = "FAIL"
                r.detail = (
                    f"CRITICAL: org B sees {count} rows in {table}. "
                    "RLS policy missing or broken — fix immediately."
                )
        finally:
            await conn.close()
    except Exception as exc:
        r.status = "ERROR"
        r.error = str(exc)[:200]
    return r


# ── A6: concurrent run safety ──────────────────────────────────────────────────
async def check_concurrent(config: dict, agent_name: str) -> CheckResult:
    r = CheckResult("A6", "Concurrent run safety (no deadlock, 2 agent_runs rows)")
    if config.get("skip_concurrent", False):
        r.status = "SKIP"
        r.detail = "Skipped: agent config sets skip_concurrent=true"
        return r

    params = config.get("happy_path_params", {})
    cmd = _run_agent_cmd(agent_name, params)
    try:
        p1 = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=str(REPO_ROOT),
        )
        p2 = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=str(REPO_ROOT),
        )
        (_, err1), (_, err2) = await asyncio.gather(p1.communicate(), p2.communicate())

        codes = [p1.returncode, p2.returncode]
        if codes[0] != 0 or codes[1] != 0:
            r.status = "FAIL"
            failures = [f"run{i+1} exit={c}" for i, c in enumerate(codes) if c != 0]
            snippet = (err1 + err2).decode(errors="replace")[-300:]
            r.detail = f"One or both runs failed: {', '.join(failures)} | {snippet.replace(chr(10), ' ')}"
            return r

        # Check agent_runs for 2 new entries
        conn = await asyncpg.connect(DB_DSN)
        try:
            await conn.execute(f"SET app.current_org_id = '{DEV_ORG_ID}'")
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM agent_runs "
                "WHERE agent_name = $1 AND started_at > now() - interval '90 seconds'",
                agent_name,
            )
        finally:
            await conn.close()

        if count >= 2:
            r.status = "PASS"
            r.detail = f"Both runs completed, {count} agent_runs entries in last 90s (no deadlock)"
        else:
            r.status = "WARN"
            r.detail = f"Only {count} agent_runs in last 90s — expected ≥2 (timing or merge issue?)"
    except Exception as exc:
        r.status = "ERROR"
        r.error = str(exc)[:300]
    return r


# ── A7: agent_runs logging accuracy ───────────────────────────────────────────
async def check_agent_runs(config: dict, agent_name: str) -> CheckResult:
    r = CheckResult("A7", "agent_runs row accuracy (status, duration, tokens)")
    uses_llm = config.get("uses_llm", False)
    has_external_dep = config.get("external_dependency", "none") not in ("none", None, "")
    try:
        conn = await asyncpg.connect(DB_DSN)
        try:
            await conn.execute(f"SET app.current_org_id = '{DEV_ORG_ID}'")
            row = await conn.fetchrow(
                "SELECT status, duration_ms, tokens_in, tokens_out, cost_usd, error "
                "FROM agent_runs WHERE agent_name = $1 ORDER BY started_at DESC LIMIT 1",
                agent_name,
            )
        finally:
            await conn.close()

        if row is None:
            r.status = "FAIL"
            r.detail = "No agent_runs row — agent never ran or BaseAgent.audit() failed"
            return r

        # Agents with external HTTP dependencies may return 'partial' when some
        # remote calls fail — that is valid behaviour, not an agent failure.
        acceptable_statuses = {"success", "partial"} if has_external_dep else {"success"}
        issues = []
        if row["status"] not in acceptable_statuses:
            issues.append(f"status={row['status']!r} (expected one of {sorted(acceptable_statuses)})")
        if (row["duration_ms"] or 0) <= 0:
            issues.append(f"duration_ms={row['duration_ms']} (must be > 0)")
        if row["error"] is not None:
            issues.append(f"error={row['error']!r} (expected NULL on success)")
        if uses_llm and (row["tokens_in"] or 0) == 0:
            issues.append("tokens_in=0 for LLM agent (should be > 0 after real LLM call)")

        if issues:
            r.status = "FAIL"
            r.detail = "; ".join(issues)
        else:
            r.status = "PASS"
            r.detail = (
                f"status={row['status']}, duration={row['duration_ms']}ms, "
                f"tokens_in={row['tokens_in']}, tokens_out={row['tokens_out']}, "
                f"cost=${row['cost_usd']:.4f}, error=None"
            )
    except Exception as exc:
        r.status = "ERROR"
        r.error = str(exc)[:300]
    return r


# ── B3: API auth enforcement ───────────────────────────────────────────────────
def check_api_auth(config: dict) -> CheckResult:
    r = CheckResult("B3", "API auth enforcement")
    ep = config.get("api_read_endpoint") or config.get("api_write_endpoint")
    if not ep:
        r.status = "SKIP"
        r.detail = "No API endpoint configured for this agent"
        return r

    method, path = (ep.split(" ", 1) + [ep])[:2] if " " in ep else ("GET", ep)
    url = f"http://localhost:8000{path}"
    bypass_active = _env_flag("DEV_AUTH_BYPASS")

    try:
        req = urllib.request.Request(url, method=method)
        actual_status: int
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                actual_status = resp.status
        except urllib.error.HTTPError as exc:
            actual_status = exc.code

        if bypass_active:
            if actual_status in (200, 201, 202):
                r.status = "PASS"
                r.detail = (
                    f"DEV_AUTH_BYPASS=true → {actual_status} (bypass working). "
                    "In production, Bearer JWT required."
                )
            else:
                r.status = "WARN"
                r.detail = f"DEV_AUTH_BYPASS=true but got {actual_status} (expected 2xx)"
        else:
            if actual_status == 401:
                r.status = "PASS"
                r.detail = "No token → 401 Unauthorized (auth enforced correctly)"
            elif actual_status == 403:
                r.status = "PASS"
                r.detail = "No token → 403 Forbidden (auth enforced)"
            else:
                r.status = "FAIL"
                r.detail = (
                    f"No token → {actual_status} (expected 401). "
                    "Endpoint may be unprotected!"
                )
    except Exception as exc:
        r.status = "ERROR"
        r.error = str(exc)[:200]
    return r


# ── B4: empty/default state shape ─────────────────────────────────────────────
def check_empty_state(config: dict) -> CheckResult:
    r = CheckResult("B4", "Default state shape (no null where [] expected)")
    ep = config.get("api_read_endpoint")
    if not ep:
        r.status = "SKIP"
        r.detail = "No read endpoint configured"
        return r

    _, path = (ep.split(" ", 1) + [ep])[:2] if " " in ep else ("GET", ep)
    url = f"http://localhost:8000{path}"

    try:
        req = urllib.request.Request(url)
        body: object
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            r.status = "SKIP"
            r.detail = f"Endpoint returned {exc.code} (likely needs auth or different env)"
            return r

        null_fields = []
        expected_lists = config.get("expected_list_fields", [])
        expected_empty_ok = config.get("expected_nullable_fields", ["id"])

        if isinstance(body, dict):
            for key, val in body.items():
                if val is None and key not in expected_empty_ok:
                    null_fields.append(key)
                if key in expected_lists and not isinstance(val, list):
                    null_fields.append(f"{key} should be list, got {type(val).__name__}")
        elif isinstance(body, list):
            pass  # empty list is valid
        else:
            null_fields.append(f"unexpected root type: {type(body).__name__}")

        if null_fields:
            r.status = "FAIL"
            r.detail = f"Unexpected null/wrong-type fields: {', '.join(null_fields)}"
        else:
            sample = json.dumps(body)[:200] if not isinstance(body, list) else f"[{len(body)} items]"
            r.status = "PASS"
            r.detail = f"Shape OK: {sample}"
    except Exception as exc:
        r.status = "ERROR"
        r.error = str(exc)[:200]
    return r


# ── B5: error response shape ───────────────────────────────────────────────────
def check_error_shape(config: dict) -> CheckResult:
    r = CheckResult("B5", "Invalid input → 4xx with detail field (no 500)")
    write_ep = config.get("api_write_endpoint")
    invalid_body = config.get("api_invalid_body")
    expected_status: int = config.get("api_invalid_expected_status", 422)

    if not write_ep or invalid_body is None:
        r.status = "SKIP"
        r.detail = "No write endpoint or invalid_body configured"
        return r

    method, path = (write_ep.split(" ", 1) + [write_ep])[:2] if " " in write_ep else ("POST", write_ep)
    url = f"http://localhost:8000{path}"
    data = (
        invalid_body.encode()
        if isinstance(invalid_body, str)
        else json.dumps(invalid_body).encode()
    )

    try:
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        actual_status: int
        body_obj: object = None
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                actual_status = resp.status
                body_obj = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            actual_status = exc.code
            try:
                body_obj = json.loads(exc.read())
            except Exception:
                body_obj = None

        issues = []
        if actual_status == 500:
            issues.append("Server returned 500 on bad input — must never happen")
        elif actual_status != expected_status:
            issues.append(f"Expected {expected_status}, got {actual_status}")
        if not isinstance(body_obj, dict) or "detail" not in body_obj:
            issues.append("Response missing 'detail' field (FastAPI standard error format)")

        if issues:
            r.status = "FAIL"
            body_repr = json.dumps(body_obj)[:200] if body_obj else "(no body)"
            r.detail = "; ".join(issues) + f" | body: {body_repr}"
        else:
            r.status = "PASS"
            r.detail = f"status={actual_status}, detail present"
    except Exception as exc:
        r.status = "ERROR"
        r.error = str(exc)[:200]
    return r


# ── Report writer ──────────────────────────────────────────────────────────────
def write_report(agent_name: str, config: dict, preflight: list[CheckResult],
                 checks: list[CheckResult], happy_run: tuple[bool, str]) -> Path:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    all_results = preflight + checks

    pass_n = sum(1 for r in all_results if r.status == "PASS")
    fail_n = sum(1 for r in all_results if r.status == "FAIL")
    warn_n = sum(1 for r in all_results if r.status in ("WARN", "ERROR"))
    skip_n = sum(1 for r in all_results if r.status == "SKIP")

    lines = [
        f"# Agent Test Report: `{agent_name}`",
        f"",
        f"**Date:** {now}  ",
        f"**Tier:** {config.get('tier', '?')}  ",
        f"**Uses LLM:** {config.get('uses_llm', False)}  ",
        f"**Output table:** `{config.get('output_table', 'n/a')}`  ",
        f"**External dep:** {config.get('external_dependency', 'none')}  ",
        f"",
        f"---",
        f"",
        f"## Pre-flight",
        f"",
    ]

    for r in preflight:
        lines.append(f"- {r.icon} **[{r.check_id}] {r.name}** — {r.detail or r.error}")

    happy_ok, happy_snippet = happy_run
    lines += [
        f"",
        f"**Happy-path run:** {'✅ succeeded' if happy_ok else '❌ FAILED'}",
    ]
    if not happy_ok:
        lines.append(f"```\n{happy_snippet[-400:]}\n```")

    lines += [
        f"",
        f"---",
        f"",
        f"## Automated Checks",
        f"",
        f"| Check | Name | Status | Detail |",
        f"|---|---|---|---|",
    ]
    for r in checks:
        detail = (r.detail or r.error or "")[:150].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{r.check_id}` | {r.name} | {r.icon} {r.status} | {detail} |")

    lines += [
        f"",
        f"**{pass_n} PASS / {fail_n} FAIL / {warn_n} WARN / {skip_n} SKIP**",
        f"",
        f"---",
        f"",
        f"## Layer C — UI Checklist (Manual)",
        f"",
        f"**Page:** `{config.get('ui_page', 'n/a')}`  ",
        f"**Component:** {config.get('ui_component', 'n/a')}",
        f"",
    ]
    for item in config.get("ui_checklist", []):
        lines.append(f"- [ ] {item}")

    fail_checks = [r for r in checks if r.status == "FAIL"]
    lines += [
        f"",
        f"---",
        f"",
        f"## Bugs Found",
        f"",
    ]
    if not fail_checks and happy_ok:
        lines.append("_(none — all checks passed)_")
    else:
        if not happy_ok:
            lines += [
                "| ID | Severity | Description |",
                "|---|---|---|",
                f"| BUG-{agent_name.upper()[:4]}-HAP | High | Happy-path CLI run failed — see snippet above |",
            ]
        for i, r in enumerate(fail_checks, 1):
            lines += (
                [] if i == 1 and happy_ok else []
            )
            if i == 1 and happy_ok:
                lines += [
                    "| ID | Check | Severity | Description |",
                    "|---|---|---|---|",
                ]
            sev = "Critical" if r.check_id == "A3" else "High"
            desc = (r.detail or r.error)[:120].replace("|", "\\|")
            lines.append(f"| BUG-{agent_name.upper()[:4]}-{r.check_id} | {r.check_id} | {sev} | {desc} |")

    report_path = REPO_ROOT / "tests" / "agent_reports" / f"{agent_name}_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n")
    return report_path


# ── Main ───────────────────────────────────────────────────────────────────────
async def _async_checks(config: dict, agent_name: str) -> list[CheckResult]:
    rls, concurrent, agent_runs_check = await asyncio.gather(
        check_rls(config),
        check_concurrent(config, agent_name),
        check_agent_runs(config, agent_name),
    )
    return [rls, concurrent, agent_runs_check]


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: _test_agent_runner.py <agent_name>")
        sys.exit(1)

    agent_name = sys.argv[1]
    config = load_config(agent_name)

    # ── Pre-flight ─────────────────────────────────────────────────────────────
    print("Pre-flight checks:")
    pf_registry = preflight_registry(agent_name)
    pf_table = preflight_table(config)
    pf_unit = preflight_unit_tests(agent_name)
    preflight = [pf_registry, pf_table, pf_unit]
    for r in preflight:
        print(f"  {r.icon} [{r.check_id}] {r.name}")
        if r.detail:
            print(f"       {r.detail[:100]}")
        if r.error:
            print(f"       ERROR: {r.error[:100]}")

    # ── Happy-path run ─────────────────────────────────────────────────────────
    print()
    print("Running happy-path CLI run (populates DB for subsequent checks)...")
    params = config.get("happy_path_params", {})
    happy_ok, happy_snippet = run_agent_once(agent_name, params, timeout=_run_timeout(config))
    if happy_ok:
        print("  ✅ Succeeded")
    else:
        print("  ❌ FAILED")
        print(f"  {happy_snippet[-300:].replace(chr(10), chr(10) + '  ')}")

    # ── Automated checks ───────────────────────────────────────────────────────
    print()
    print("Running automated checks:")
    async_results = asyncio.run(_async_checks(config, agent_name))
    sync_results = [check_api_auth(config), check_empty_state(config), check_error_shape(config)]
    all_checks = async_results + sync_results

    for r in all_checks:
        print(f"  {r.icon} [{r.check_id}] {r.name}")
        if r.detail:
            print(f"       {r.detail[:110]}")
        if r.error:
            print(f"       ERROR: {r.error[:110]}")

    # ── UI checklist ───────────────────────────────────────────────────────────
    print()
    print("Layer C — UI checklist (manual verification required):")
    for item in config.get("ui_checklist", []):
        print(f"  [ ] {item}")

    # ── Write report ───────────────────────────────────────────────────────────
    report_path = write_report(agent_name, config, preflight, all_checks, (happy_ok, happy_snippet))
    print()
    print(f"Report: {report_path.relative_to(REPO_ROOT)}")

    # ── Summary ────────────────────────────────────────────────────────────────
    fails = [r for r in all_checks if r.status == "FAIL"]
    if not fails and happy_ok:
        print("Result: ✅ ALL CHECKS PASSED")
    else:
        print(f"Result: ❌ {len(fails)} FAIL(s) — see report for bug details")
        sys.exit(1)


if __name__ == "__main__":
    main()
