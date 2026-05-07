# Test Summary

**Last updated:** 2026-05-07 (keyword_research + keyword_validator — tier testing paused)  
**Test harness:** `scripts/test_agent.sh <agent_name>`  
**Config files:** `tests/agent_configs/{agent}.yaml`  
**Reports:** `tests/agent_reports/{agent}_report.md`

---

## Agents Tested

| Agent | Layer A (Unit) | Layer B (Automated) | Layer C (UI) | Verdict |
|---|---|---|---|---|
| brand_voice_keeper | ✅ 8/8 pass | ✅ 6/6 pass | ⚠️ 1 open bug | CONDITIONAL |
| competitor_monitor | ✅ 20/20 pass | ✅ 8/8 pass (A6 skip) | ✅ 4 bugs fixed | APPROVED |
| keyword_research | ✅ pass | ✅ pass | ⚠️ Tier 1+2 untested | CONDITIONAL |
| keyword_validator | ✅ pass | ✅ pass | ⚠️ Tier 1+2 untested | CONDITIONAL |
| opportunity_scorer | ✅ 8/8 pass | ✅ 6/6 pass | ⬜ pending manual check | APPROVED |

**Note:** keyword_research and keyword_validator Tier 1 (DataForSEO) and Tier 2 (Keywords Everywhere) integration tests are paused — APIs are not yet funded. Tier 3 (AnchorScaleEstimator) and Tier 4 (pending) paths are unit-tested and verified. Will resume when API billing is set up.

---

## Open Bugs

| ID | Agent | Layer | Severity | Summary | Status |
|---|---|---|---|---|---|
| BUG-UI-003 | brand_voice_keeper | C — UI | Medium | `style_rules` not rendered in Settings form; users cannot view or edit via UI | Open |
| BUG-UI-005 | competitor_monitor | C — UI | Medium | Domain stored with `https://` prefix; normalisation incomplete | ✅ Fixed |
| BUG-UI-006 | competitor_monitor | C — UI | Medium | Duplicate competitor not detected client-side | ✅ Fixed |
| BUG-UI-009 | competitor_monitor | C — UI | Low | No crawl status indicator; plain text only | ✅ Fixed |
| BUG-UI-010 | competitor_monitor | C — UI | Low | Single empty state for no-data vs no-search-match | ✅ Fixed |
| BUG-API-001 | competitor_monitor | B — API | Medium | `POST /api/v1/competitors` accepted nonexistent/garbage domains; no DNS check | ✅ Fixed |
| BUG-A-004 | opportunity_scorer | B — API | High | `GET /api/v1/opportunities` returned 500 — asyncpg rejects `::uuid[]` cast on bind param | ✅ Fixed |
| BUG-UI-014 | keywords | C — UI | Low | Volume trend graph empty even with data present | Open |
| BUG-UI-018 | keyword_validator | C — UI | Low | Row highlight after single-keyword validation does not clear automatically | Open |
| BUG-UI-019 | keyword_validator | C — UI | Low | Ollama model name exposed in banner/error messages; should be abstracted | Open |
| BUG-UI-020 | keyword_validator | C — UI | Low | Source badge mapping: `llm_estimate` not mapped to amber "Metrics pending" in all badge paths | Open |

---

## Pending Testing

| Item | Blocked By | Priority |
|---|---|---|
| keyword_research Tier 1 — DataForSEO live call | DataForSEO API funding | High |
| keyword_research Tier 2 — Keywords Everywhere live call | Keywords Everywhere API funding | Medium |
| keyword_validator Tier 1+2 metrics true-up path | Above APIs | High |
| keyword_validator `pending_metrics` → re-validate flow (end-to-end) | Above APIs | High |

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

1. ~~brand_voice_keeper~~ ✅ Done (CONDITIONAL — BUG-UI-003 open)
2. ~~competitor_monitor~~ ✅ Done (APPROVED)
3. ~~keyword_research~~ ✅ Done (CONDITIONAL — Tier 1+2 paused)
4. ~~keyword_validator~~ ✅ Done (CONDITIONAL — Tier 1+2 paused)
5. ~~opportunity_scorer~~ ✅ Done (APPROVED — BUG-A-004 fixed)
6. content_extractor
7. trend_collector
8. keyword_overlap_analyzer
9. site_auditor
10. rank_tracker
11. ... (continue through 34 agents)
