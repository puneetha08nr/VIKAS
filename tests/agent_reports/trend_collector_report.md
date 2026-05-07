# Agent Test Report: `trend_collector`

**Date:** 2026-05-07 12:51 UTC  
**Tier:** fast  
**Uses LLM:** False  
**Output table:** `trend_signals`  
**External dep:** pytrends  

---

## Pre-flight

- ✅ **[P1] Agent in registry** — Agent registered via @register decorator
- ✅ **[P2] Output table exists (trend_signals)** — Table public.trend_signals exists
- ✅ **[A1] Unit tests pass** — 15 passed in 2.93s

**Happy-path run:** ✅ succeeded

---

## Automated Checks

| Check | Name | Status | Detail |
|---|---|---|---|
| `A3` | RLS isolation (org B sees 0 rows) | ✅ PASS | Org B sees 0 rows in trend_signals — RLS enforced |
| `A6` | Concurrent run safety (no deadlock, 2 agent_runs rows) | ⬜ SKIP | Skipped: agent config sets skip_concurrent=true |
| `A7` | agent_runs row accuracy (status, duration, tokens) | ✅ PASS | status=success, duration=1754ms, tokens_in=0, tokens_out=0, cost=$0.0000, error=None |
| `B3` | API auth enforcement | ⬜ SKIP | No API endpoint configured for this agent |
| `B4` | Default state shape (no null where [] expected) | ⬜ SKIP | No read endpoint configured |
| `B5` | Invalid input → 4xx with detail field (no 500) | ⬜ SKIP | No write endpoint or invalid_body configured |

**5 PASS / 0 FAIL / 0 WARN / 4 SKIP**

---

## Layer C — UI Checklist (Manual)

**Page:** `/dashboard`  
**Component:** Trend signals widget

- [ ] Dashboard shows recent trend signals or 'no trends' empty state
- [ ] Trend signals have source label (google_trends, reddit, etc.)
- [ ] Momentum values are numeric (0–10 scale)

---

## Bugs Found

_(none — all checks passed)_
