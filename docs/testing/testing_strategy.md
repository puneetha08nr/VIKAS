

# VIKAS — End-to-End Testing Strategy

Senior testing engineer perspective. One agent per session. Real DB, real LLM, no mocks.
Phase-specific detail lives in `testing_phase<N>_<agent>.md` files alongside this one.

---

## Mental Model: Production Pipeline

Before a single agent runs, three things must be true for any org:

```
1. Organization row exists            → all agents scoped to org_id
2. brand_voice row exists             → content agents pull tone/vocabulary
3. At least one LLM tier is reachable → agents can call_llm()
```

Two entry points in production:

```
Manual trigger:
  brand_voice_keeper
    → keyword_research → keyword_validator → gap_analyzer → opportunity_scorer
    → content_director
        ├── article_planner → article_writer → internal_link_finder
        ├── linkedin_agent
        ├── twitter_agent
        └── newsletter_agent
    → human review → wordpress_publisher

Auto mode (nightly 2 AM UTC):
  trend_collector + competitor_monitor  (parallel)
    → opportunity_scorer → content_director → same content branch
```

brand_voice is the dependency of everything in the content branch.
opportunity is the dependency of content_director and everything below it.
Nothing downstream exists until upstream writes to DB.

---

## Testing Philosophy

- **One agent = one session.** Fully verify before moving to the next.
- **Real DB, real LLM, no mocks.** Unit tests with mocks already pass. This proves the system works end-to-end under real conditions.
- **Start dirty, end clean.** Intentionally break inputs first (cold DB, empty params, bad LLM response shapes), then run the golden path. Bugs hide in error paths.
- **DB is the source of truth.** Every agent run is verified by SQL queries, not just `AgentResult.status`.
- **RLS is always checked.** After every successful write, verify a second org sees 0 rows from the same table.
- **Idempotency.** Running the same agent twice must not corrupt data or double-insert rows.

---

## Standard Verification Checklist (Every Agent)

Run after every agent execution:

```sql
-- 1. Rows written with correct org
SET app.current_org_id = '<test-org-id>';
SELECT * FROM <table> ORDER BY created_at DESC LIMIT 10;

-- 2. agent_runs audit row
SELECT agent_name, status, tokens_in, tokens_out, duration_ms, cost_usd, error
FROM agent_runs ORDER BY started_at DESC LIMIT 3;

-- 3. RLS — second org must see 0 rows
SET app.current_org_id = '99999999-9999-9999-9999-999999999999';
SELECT COUNT(*) FROM <table>;  -- must return 0
```

CLI run pattern:
```bash
python scripts/run_agent.py \
  --agent <name> \
  --params '{"key": "value"}' \
  --org 00000000-0000-0000-0000-000000000001
```

---

## Systemic Risks — Watch Across All Agents

| Risk | Description |
|---|---|
| Cold start | First run on a fresh org: no brand_voice, no keywords, no opportunities. Each agent must degrade gracefully. |
| LLM schema drift | LLM occasionally returns a slightly different JSON shape. Defensive parser is the only safety net. |
| Partial write silent failure | Agent writes 7/10 rows, reports `found: 10`. Invisible unless DB rows counted explicitly after run. |
| RLS misconfiguration | Wrong policy means one org's content leaks to another. Easy to miss during dev. |
| internal_link_finder chicken-and-egg | First article has no sibling articles to link to. Must return empty gracefully. |
| preference_learner with no feedback | No `content_feedback` rows yet. Should return `success` with 0 patterns, not crash. |
| asyncpg `::type` cast syntax | Named params + `::vector` / `::jsonb` suffix breaks asyncpg. Always use `CAST(:param AS type)`. |
| Lazy imports not in pyproject.toml | `import pypdf` inside a function still requires the package declared in dependencies. |

---

## Agent Test Sequence

| Phase | Agent | Gate |
|---|---|---|
| 0 | **Infrastructure verification** | Docker, DB schema, RLS, registry, env vars — must pass before any agent test |
| 1 | `brand_voice_keeper` | Must run first — content agents depend on it |
| 1a | `keyword_research` | Entry point of content pipeline |
| 1b | `keyword_validator` | Needs Phase 1a output |
| 1c | `gap_analyzer` | Needs Phase 1b output |
| 1d | `opportunity_scorer` | Needs Phase 1c output |
| 2a | `competitor_monitor` | Can run parallel to Phase 1 in prod |
| 2b | `content_extractor` | Needs Phase 2a output |
| 2c | `keyword_overlap_analyzer` | Needs Phase 2b + Phase 1a output |
| 2d | `threat_assessor` | Needs Phase 2c output |
| 3a | `content_director` | Needs Phase 1d opportunity |
| 3b | `article_planner` | Dispatched by content_director |
| 3c | `article_writer` | Needs Phase 3b output |
| 3d | `linkedin_agent` | Needs Phase 3b output |
| 3e | `twitter_agent` | Needs Phase 3b output |
| 3f | `newsletter_agent` | Needs Phase 3b output |
| 4a | `internal_link_finder` | Needs Phase 3c output (edge: first article) |
| 4b | `wordpress_publisher` | Needs approved content_item |
| 5 | `preference_learner` | Needs feedback rows from human review |

---

## Phase Index

| File | Covers |
|---|---|
| `testing_phase0_infrastructure.md` | Docker stack, DB schema, RLS audit, registry, env vars, known infra issues |
| `testing_phase1_brand_voice.md` | brand_voice_keeper — edge cases, SQL, findings |
| `testing_phase2_seo_discovery.md` | keyword_research, keyword_validator, gap_analyzer, opportunity_scorer |
| `testing_phase3_competitor_intel.md` | competitor_monitor, content_extractor, keyword_overlap_analyzer, threat_assessor |
| `testing_phase4_content_production.md` | content_director, article_planner, article_writer, social agents |
| `testing_phase5_publishing.md` | internal_link_finder, wordpress_publisher |
| `testing_phase6_learning_loop.md` | preference_learner |
