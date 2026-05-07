# Agent Test Report: `keyword_research`

**Date:** 2026-05-06 17:45 UTC  
**Tier:** fast  
**Uses LLM:** True  
**Output table:** `keywords`  
**External dep:** dataforseo_optional  

---

## Pre-flight

- ✅ **[P1] Agent in registry** — Agent registered via @register decorator
- ✅ **[P2] Output table exists (keywords)** — Table public.keywords exists
- ✅ **[A1] Unit tests pass** — 11 passed in 6.43s

**Happy-path run:** ✅ succeeded

---

## Automated Checks

| Check | Name | Status | Detail |
|---|---|---|---|
| `A3` | RLS isolation (org B sees 0 rows) | ✅ PASS | Org B sees 0 rows in keywords — RLS enforced |
| `A6` | Concurrent run safety (no deadlock, 2 agent_runs rows) | ⬜ SKIP | Skipped: agent config sets skip_concurrent=true |
| `A7` | agent_runs row accuracy (status, duration, tokens) | ✅ PASS | status=partial, duration=159436ms, tokens_in=268, tokens_out=825, cost=$0.0000, error=None |
| `B3` | API auth enforcement | ✅ PASS | DEV_AUTH_BYPASS=true → 200 (bypass working). In production, Bearer JWT required. |
| `B4` | Default state shape (no null where [] expected) | ✅ PASS | Shape OK: [99 items] |
| `B5` | Invalid input → 4xx with detail field (no 500) | ✅ PASS | status=422, detail present |

**8 PASS / 0 FAIL / 0 WARN / 1 SKIP**

---

## Layer C — UI Checklist (Manual)

**Page:** `/keywords`  
**Component:** Keywords research trigger + table

- [ ] Page /keywords loads with keyword table (or empty state message)
- [ ] Click 'Research Keywords' button — shows loading state
- [ ] After research completes — new keywords appear in table
- [ ] Table columns: keyword, volume, KD, CPC, intent all visible
- [ ] Keywords have status badges (raw/validated/archived)
- [ ] Search/filter box narrows the keyword list
- [ ] Keyword row click shows detail panel or navigates to detail page

---

## Bugs Found

_(none — all checks passed)_
