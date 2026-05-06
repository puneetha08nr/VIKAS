# Phase 0 — Infrastructure Verification

Pre-condition for all agent testing. If anything in this phase fails, agent test results are unreliable.
Run this checklist fresh after every Docker rebuild or env change.

---

## Current Stack State (verified 2026-05-06)

| Container | Image | Status |
|---|---|---|
| vikas-api-1 | vikas-api | healthy |
| vikas-db-1 | pgvector/pgvector:pg16 | healthy |
| vikas-redis-1 | redis:7-alpine | healthy |
| vikas-worker-1 | vikas-worker | up (no healthcheck) |

---

## Verification Areas

### 1. Docker Stack Health

**Command:**
```bash
docker compose -f infra/docker/docker-compose.yml ps
```

**Pass criteria:**
- `vikas-api-1` → `healthy`
- `vikas-db-1` → `healthy`
- `vikas-redis-1` → `healthy`
- `vikas-worker-1` → `up` (worker has no healthcheck — verify via logs)

**Red flags:**
- Any container in `unhealthy` or `restarting` → check `docker logs <container>`
- Worker container is critical for Celery task dispatch — if it's down, pipeline_orchestrator and auto_mode_engine will silently fail to dispatch tasks

---

### 2. API Reachability

**Command:**
```bash
curl http://localhost:8000/health
```

**Pass:** `{"status":"ok"}`

**Also verify route count:**
```bash
curl -s http://localhost:8000/openapi.json | python3 -c "
import sys, json; spec = json.load(sys.stdin)
print(f'Routes registered: {len(spec[\"paths\"])}')"
```

**Expected:** 30 routes. A drop means a router wasn't imported or an agent endpoint crashed on registration.

**Known failure mode:** If any FastAPI route uses `UploadFile`, `File()`, or `Form()` and `python-multipart` is not installed, the entire API fails at startup with `RuntimeError` — not just that endpoint. Zero routes will be accessible. (See ISSUES_AND_FIXES Issue 37)

---

### 3. PostgreSQL — Connectivity + Schema

**Command:**
```bash
python3 -c "
import asyncio, asyncpg
async def check():
    conn = await asyncpg.connect('postgresql://vikas_app:vikas_app_dev@localhost:5432/vikas')
    ver = await conn.fetchval('SELECT version()')
    count = await conn.fetchval(\"SELECT COUNT(*) FROM pg_tables WHERE schemaname='public'\")
    print(f'Connected: {ver[:50]}')
    print(f'Public tables: {count}')
    await conn.close()
asyncio.run(check())
"
```

**Pass criteria:**
- Connects without error
- 19 tables present (see table list below)
- pgvector extension installed

**Current table inventory (19 tables):**
```
agent_runs, alembic_version, brand_voice, competitor_content, competitors,
content_items, content_reviews, evals_log, keyword_clusters, keywords,
knowledge_chunks, opportunities, organizations, pipeline_runs, preferences,
prompts, rank_tracking, site_audits, trend_signals
```

**Missing tables** — agents that have migrations not yet applied OR whose tables were skipped:

| Missing Table | Blocks Agent |
|---|---|
| `articles` | article_writer, article_planner (uses content_items instead — verify) |
| `article_plans` | article_planner |
| `social_content` / `linkedin_posts` / `twitter_threads` / `newsletters` | social agents |
| `lead_magnets` | lead_magnet_agent |
| `broll_suggestions` | broll_selector |
| `strategy_reports` | strategy_synthesizer |
| `topics` | topic_discovery |
| `video_jobs` | video_handoff, broll_selector |
| `aeo_results` | aeo_scanner |

> **Action before Phase 1:** Run `uv run alembic upgrade head` and recount tables.

---

### 4. Alembic Migration Status

**Command:**
```bash
cd apps/api && uv run alembic current && uv run alembic heads
```

**Pass:** `current` and `heads` return the same revision. Any divergence means unapplied migrations.

**Current head:** `c4d5e6f7a8b9`

**Red flag:** Two heads means a migration was written with the wrong `down_revision`. See ISSUES_AND_FIXES Issue 13.

---

### 5. Row-Level Security — Policy Coverage Audit

**Current state (verified):**

| Table | RLS Policy |
|---|---|
| agent_runs | ✅ |
| brand_voice | ✅ |
| competitor_content | ✅ |
| competitors | ✅ |
| content_items | ✅ |
| content_reviews | ✅ |
| keyword_clusters | ✅ |
| keywords | ✅ |
| knowledge_chunks | ✅ |
| opportunities | ✅ |
| pipeline_runs | ✅ |
| preferences | ✅ |
| rank_tracking | ✅ |
| site_audits | ✅ |
| trend_signals | ✅ |
| **organizations** | ❌ intentional — orgs are looked up by auth, not RLS |
| **prompts** | ❌ intentional — prompts are shared across orgs |
| **evals_log** | ❌ intentional — operational data, not tenant data |
| **alembic_version** | ❌ system table |

**RLS functional test:**
```sql
-- Write as org A
SET app.current_org_id = '00000000-0000-0000-0000-000000000001';
INSERT INTO keywords (id, org_id, keyword, status, source_agent, created_at, updated_at)
VALUES (gen_random_uuid(), current_setting('app.current_org_id')::uuid,
        'rls-test', 'raw', 'test', now(), now());

-- Read as org B — must return 0
SET app.current_org_id = '99999999-9999-9999-9999-999999999999';
SELECT COUNT(*) FROM keywords WHERE keyword = 'rls-test';  -- expect 0

-- Cleanup
SET app.current_org_id = '00000000-0000-0000-0000-000000000001';
DELETE FROM keywords WHERE keyword = 'rls-test';
```

---

### 6. Redis Connectivity

**Command:**
```bash
python3 -c "import redis; r = redis.Redis(host='localhost', port=6379); print('Redis ping:', r.ping())"
```

**Pass:** `Redis ping: True`

**Why this matters:** `pipeline_orchestrator` and `auto_mode_engine` dispatch tasks via Celery → Redis. If Redis is down, those agents appear to succeed (task dispatched) but nothing executes. Silent failure.

---

### 7. Agent Registry — Coverage Check

**Command:**
```bash
cd apps/api && python3 -c "
from core.agent_registry import REGISTRY, import_all_agents
import_all_agents()
print(f'Registered: {len(REGISTRY)}')
for name in sorted(REGISTRY): print(f'  {name}')
"
```

**Current state:** 24 of 34 expected agents are registered.

**Agents NOT in registry (missing `@register` or not imported in `import_all_agents`):**

| Agent | Likely reason |
|---|---|
| `competitor_discovery` | Not imported in `import_all_agents()` |
| `pipeline_orchestrator` | Not imported in `import_all_agents()` |
| `ai_assistant` | Not imported in `import_all_agents()` |
| `twitter_agent` | Not imported in `import_all_agents()` |
| `newsletter_agent` | Not imported in `import_all_agents()` |
| `video_scriptwriter` | Not imported in `import_all_agents()` |
| `lead_magnet_agent` | Not imported in `import_all_agents()` |
| `strategy_synthesizer` | Not imported in `import_all_agents()` |
| `auto_mode_engine` | Not imported in `import_all_agents()` |
| `broll_selector` | Not imported in `import_all_agents()` |

> **Action:** These must be added to `import_all_agents()` in `core/agent_registry.py`
> before those agents can be triggered via CLI or API.

---

### 8. Environment Variables

**Command:**
```bash
python3 -c "
import os; from dotenv import load_dotenv; load_dotenv('apps/api/.env')
keys = ['DATABASE_URL','ADMIN_DATABASE_URL','REDIS_URL','OPENAI_API_KEY','ANTHROPIC_API_KEY']
for k in keys:
    v = os.getenv(k, '')
    status = 'SET' if v and 'placeholder' not in v.lower() else 'MISSING'
    print(f'{k}: {status}')
"
```

**Current state:** All five critical keys are SET.

**Optional keys** (agents degrade gracefully if missing, but log warnings):
```
GOOGLE_AI_API_KEY       → Google LLM tier unavailable
GSC_SERVICE_ACCOUNT_JSON → rank_tracker, keyword_research GSC features disabled
WORDPRESS_URL / WORDPRESS_APP_PASSWORD → wordpress_publisher returns failed
SLACK_WEBHOOK_URL       → notifications silently skipped (not a failure)
SMTP_HOST / SMTP_USER   → email integration skipped
```

---

### 9. Prompts Table — Seeded Check

**Command:**
```sql
SELECT agent_name, version, active FROM prompts ORDER BY agent_name;
```

**Current state:** 11 prompts seeded.

**Agents that require a prompt but may be missing:**

Any agent that calls `await PromptRegistry().get(self.name, ctx.db)` will raise `PromptNotFoundError` if its row is absent. This surfaces as `status=failed` in `agent_runs`, not a crash.

Verify before each agent test: `SELECT COUNT(*) FROM prompts WHERE agent_name = '<name>';`

---

### 10. Celery Worker — Task Dispatch Verification

**Command:**
```bash
docker logs --tail 30 vikas-worker-1
```

**Pass:** No `ERROR` lines, shows `[tasks]` list on startup, shows `celery@... ready`.

**Edge case:** Worker starts but has import errors for specific task modules → those tasks silently fail. Check `docker logs vikas-worker-1 | grep -i "error\|import"`.

---

## Infrastructure Issues Found (2026-05-06)

### INFRA-01 — 10 agents missing from `import_all_agents()` in agent_registry.py

**Severity:** High  
**Impact:** These agents cannot be triggered via `scripts/run_agent.py` or the `/api/v1/agents/{name}/run` endpoint. The call fails with `KeyError: Agent 'X' not found in registry`.  
**Agents affected:** competitor_discovery, pipeline_orchestrator, ai_assistant, twitter_agent, newsletter_agent, video_scriptwriter, lead_magnet_agent, strategy_synthesizer, auto_mode_engine, broll_selector  
**Fix required:** Add missing module paths to `import_all_agents()` before Phase 3 testing.

### INFRA-02 — Several tables missing from DB (19 present, expected ~28)

**Severity:** High  
**Impact:** Agents that write to missing tables will fail at the INSERT step, not at startup. The failure appears in `agent_runs` as `status=failed` with a `UndefinedTableError`. Migrations for these tables exist (in `db/migrations/versions/`) but have not been applied.  
**Fix required:** `uv run alembic upgrade head` from `apps/api/`. Recount tables after.

### INFRA-03 — Celery worker has no healthcheck in docker-compose

**Severity:** Medium  
**Impact:** If the worker crashes and restarts in a loop, `docker compose ps` still shows `Up`. Tasks appear dispatched but never execute. Silent failure in pipeline_orchestrator and auto_mode_engine.  
**Fix required:** Add a healthcheck to the worker service in `docker-compose.yml` (e.g. `celery -A workers.celery_app inspect ping`).

---

## Phase 0 Sign-Off Checklist

Before moving to Phase 1 (brand_voice_keeper):

- [ ] All 4 containers healthy / up
- [ ] `curl http://localhost:8000/health` → `{"status":"ok"}`
- [ ] 30 API routes registered
- [ ] `alembic current` == `alembic heads` (no pending migrations)
- [ ] All expected tables present (recount after `alembic upgrade head`)
- [ ] RLS functional test passes (org B sees 0 rows from org A's keywords)
- [ ] 34 agents in registry (after fixing `import_all_agents`)
- [ ] All 5 critical env vars SET
- [ ] Prompts seeded for agents under test
- [ ] Worker logs clean (no errors)
