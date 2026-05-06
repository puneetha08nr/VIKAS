# Test Summary

**Last updated:** 2026-05-06  
**Test harness:** `scripts/test_agent.sh <agent_name>`  
**Config files:** `tests/agent_configs/{agent}.yaml`  
**Reports:** `tests/agent_reports/{agent}_report.md`

---

## Agents Tested

| Agent | Layer A (Unit) | Layer B (Automated) | Layer C (UI) | Bugs Found |
|---|---|---|---|---|
| brand_voice_keeper | ✅ 8/8 pass | ✅ 6/6 pass | ❌ 2 gaps | BUG-UI-003, FEATURE: target_audience |

**Total:** 1 agent fully tested (automated), 1 agent UI-diagnosed (manual checklist pending).

---

## Open Bugs

| ID | Agent | Layer | Severity | Summary | Status |
|---|---|---|---|---|---|
| BUG-UI-003 | brand_voice_keeper | C — UI | Medium | `style_rules` not rendered in Settings form; users cannot view or edit via UI | Open |

---

## Feature Gaps (not bugs)

| ID | Agent | Summary |
|---|---|---|
| FEAT-001 | brand_voice_keeper | `target_audience` field — not built at any layer (DB, agent, UI). Future backlog item. |

---

## Infrastructure (Phase 0) — Resolved

| Issue | Fix | Status |
|---|---|---|
| INFRA-01: Only 24 agents in registry | Added `import_all_agents()` to `run_agent.py` | ✅ Resolved |
| INFRA-02: Alembic migrations failing (asyncpg multi-statement) | Split `ALTER TABLE ... ENABLE RLS; CREATE POLICY` into two `op.execute()` calls across 10 migration files | ✅ Resolved |
| INFRA-03: Worker container no healthcheck | Added healthcheck to `docker-compose.yml` | ✅ Resolved |

---

## Test Harness Coverage

The harness (`scripts/_test_agent_runner.py`) runs 6 automated checks per agent:

| Check | Description |
|---|---|
| A3 | RLS isolation — org B sees 0 rows in output table |
| A6 | Concurrent run safety — 2 parallel runs, no deadlock, correct `agent_runs` count |
| A7 | `agent_runs` row accuracy — status, duration_ms, tokens_in/out, error column |
| B3 | API auth enforcement — 200 with `DEV_AUTH_BYPASS=true`; note: prod requires JWT |
| B4 | Default state shape — no null where list/object expected |
| B5 | Invalid input → 4xx with `detail` field (no 500) |

Not all checks apply to every agent. Config YAML controls which are active via `has_rls`, `api_invalid_body`, etc.

---

## Next Agent Queue

Order follows the protocol: fast-tier, no-LLM agents first.

1. ~~brand_voice_keeper~~ ✅ Done
2. competitor_monitor
3. content_extractor
4. opportunity_scorer
5. trend_collector
6. keyword_overlap_analyzer
7. site_auditor
8. rank_tracker
9. ... (continue through 34 agents)
