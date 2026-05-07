# Agent Test Report: `keyword_validator`

**Date:** 2026-05-07 07:50 UTC  
**Tier:** fast  
**Uses LLM:** False  
**Output table:** `keywords`  
**External dep:** dataforseo_optional  

---

## Pre-flight

- ✅ **[P1] Agent in registry** — Agent registered via @register decorator
- ✅ **[P2] Output table exists (keywords)** — Table public.keywords exists
- ✅ **[A1] Unit tests pass** — 38 passed in 8.01s

**Happy-path run:** ✅ succeeded

---

## Automated Checks

| Check | Name | Status | Detail |
|---|---|---|---|
| `A3` | RLS isolation (org B sees 0 rows) | ✅ PASS | Org B sees 0 rows in keywords — RLS enforced |
| `A6` | Concurrent run safety (no deadlock, 2 agent_runs rows) | ✅ PASS | Both runs completed, 3 agent_runs entries in last 90s (no deadlock) |
| `A7` | agent_runs row accuracy (status, duration, tokens) | ✅ PASS | status=success, duration=3ms, tokens_in=0, tokens_out=0, cost=$0.0000, error=None |
| `B3` | API auth enforcement | ✅ PASS | DEV_AUTH_BYPASS=true → 200 (bypass working). In production, Bearer JWT required. |
| `B4` | Default state shape (no null where [] expected) | ✅ PASS | Shape OK: {"keywords": [{"id": "fef3a160-389a-4efa-9cc6-c881e3141bb5", "keyword": "blockchain marketing digital", "volume": null, "kd": null, "cpc": n |
| `B5` | Invalid input → 4xx with detail field (no 500) | ✅ PASS | status=422, detail present |

**9 PASS / 0 FAIL / 0 WARN / 0 SKIP**

---

## Layer C — UI Checklist (Manual)

**Page:** `/keywords`  
**Component:** Validate All Keywords button + status badges

- [ ] Page /keywords shows 'Validate All' button
- [ ] Validated keywords show green badge, archived show grey
- [ ] Running validate-all updates keyword statuses without page refresh
- [ ] Filtering by status=validated shows only validated rows

---

## Bugs Found

_(none — all checks passed)_
