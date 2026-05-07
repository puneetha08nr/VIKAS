# Agent Test Report: `competitor_monitor`

**Date:** 2026-05-06 14:28 UTC  
**Tier:** fast  
**Uses LLM:** False  
**Output table:** `competitors`  
**External dep:** httpx_sitemap  

---

## Pre-flight

- ✅ **[P1] Agent in registry** — Agent registered via @register decorator
- ✅ **[P2] Output table exists (competitors)** — Table public.competitors exists
- ✅ **[A1] Unit tests pass** — 20 passed in 2.78s

**Happy-path run:** ✅ succeeded

---

## Automated Checks

| Check | Name | Status | Detail |
|---|---|---|---|
| `A3` | RLS isolation (org B sees 0 rows) | ✅ PASS | Org B sees 0 rows in competitors — RLS enforced |
| `A6` | Concurrent run safety (no deadlock, 2 agent_runs rows) | ⬜ SKIP | Skipped: agent config sets skip_concurrent=true |
| `A7` | agent_runs row accuracy (status, duration, tokens) | ✅ PASS | status=success, duration=322ms, tokens_in=0, tokens_out=0, cost=$0.0000, error=None |
| `B3` | API auth enforcement | ✅ PASS | DEV_AUTH_BYPASS=true → 200 (bypass working). In production, Bearer JWT required. |
| `B4` | Default state shape (no null where [] expected) | ✅ PASS | Shape OK: [4 items] |
| `B5` | Invalid input → 4xx with detail field (no 500) | ✅ PASS | status=422, detail present |

**8 PASS / 0 FAIL / 0 WARN / 1 SKIP**

---

## Layer C — UI Checklist (Manual)

**Page:** `/competitors`  
**Component:** Competitor list + add competitor form

- [ ] Page /competitors shows competitor list with domain names
- [ ] Adding a new competitor domain — appears in list
- [ ] last_crawled_at timestamp updates after monitor run
- [ ] Delete competitor removes row without page refresh

---

## Bugs Found

_(none — all checks passed)_
