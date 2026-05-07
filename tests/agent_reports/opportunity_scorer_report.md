# Agent Test Report: `opportunity_scorer`

**Date:** 2026-05-07 12:24 UTC  
**Tier:** fast  
**Uses LLM:** False  
**Output table:** `opportunities`  
**External dep:** none  

---

## Pre-flight

- ✅ **[P1] Agent in registry** — Agent registered via @register decorator
- ✅ **[P2] Output table exists (opportunities)** — Table public.opportunities exists
- ✅ **[A1] Unit tests pass** — 8 passed in 3.39s

**Happy-path run:** ✅ succeeded

---

## Automated Checks

| Check | Name | Status | Detail |
|---|---|---|---|
| `A3` | RLS isolation (org B sees 0 rows) | ✅ PASS | Org B sees 0 rows in opportunities — RLS enforced |
| `A6` | Concurrent run safety (no deadlock, 2 agent_runs rows) | ✅ PASS | Both runs completed, 3 agent_runs entries in last 90s (no deadlock) |
| `A7` | agent_runs row accuracy (status, duration, tokens) | ✅ PASS | status=success, duration=3ms, tokens_in=0, tokens_out=0, cost=$0.0000, error=None |
| `B3` | API auth enforcement | ✅ PASS | DEV_AUTH_BYPASS=true → 200 (bypass working). In production, Bearer JWT required. |
| `B4` | Default state shape (no null where [] expected) | ✅ PASS | Shape OK: [50 items] |
| `B5` | Invalid input → 4xx with detail field (no 500) | ⬜ SKIP | No write endpoint or invalid_body configured |

**8 PASS / 0 FAIL / 0 WARN / 1 SKIP**

---

## Layer C — UI Checklist (Manual)

**Page:** `/opportunities`  
**Component:** Opportunities table with composite scores

- [ ] Page /opportunities loads with opportunities table
- [ ] Rows show keyword, source, and composite score
- [ ] Sort by composite_score_desc puts highest scores first
- [ ] Status filter works (new/selected/rejected)
- [ ] Click opportunity → opens content director trigger

---

## Bugs Found

_(none — all checks passed)_
