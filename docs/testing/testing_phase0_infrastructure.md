# Phase 0 — Infrastructure Verification

Pre-condition for all agent testing. If anything in this phase fails, agent test results are unreliable.
Run this checklist fresh after every Docker rebuild or env change.

---

## Current Stack State (verified 2026-05-06, updated after Phase 0 fixes)

| Container | Image | Status |
|---|---|---|
| vikas-api-1 | vikas-api | healthy |
| vikas-db-1 | pgvector/pgvector:pg16 | healthy |
| vikas-redis-1 | redis:7-alpine | healthy |
| vikas-worker-1 | vikas-worker | up (healthcheck added — restart container to activate) |

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
- 33 tables present (see table list below)
- pgvector extension installed

**Current table inventory (33 tables, verified 2026-05-06):**
```
aeo_results, agent_runs, alembic_version, article_plans, articles, brand_voice,
broll_suggestions, competitor_content, competitors, content_feedback, content_items,
content_reviews, evals_log, keyword_clusters, keywords, knowledge_chunks,
lead_magnets, linkedin_posts, newsletters, opportunities, organizations,
pipeline_runs, preference_summaries, preferences, prompts, rank_tracking,
site_audits, strategy_reports, topics, trend_signals, twitter_threads,
video_jobs, video_scripts
```

All previously missing tables now present after `alembic upgrade head` completed cleanly.

---

### 4. Alembic Migration Status

**Command:**
```bash
cd apps/api && uv run alembic current && uv run alembic heads
```

**Pass:** `current` and `heads` return the same revision. Any divergence means unapplied migrations.

**Current head:** `a3b4c5d6e7f8` (verified — `current` == `heads`)

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
| aeo_results | ✅ |
| article_plans | ✅ |
| articles | ✅ |
| broll_suggestions | ✅ |
| content_feedback | ✅ |
| lead_magnets | ✅ |
| linkedin_posts | ✅ |
| newsletters | ✅ |
| preference_summaries | ✅ |
| strategy_reports | ✅ |
| topics | ✅ |
| twitter_threads | ✅ |
| video_jobs | ✅ |
| video_scripts | ✅ |
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

**Current state:** 34 of 34 agents registered (INFRA-01 resolved 2026-05-06).

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

### INFRA-01 — 10 agents missing from `import_all_agents()` ✅ RESOLVED

**Severity:** High  
**Impact:** These agents cannot be triggered via `scripts/run_agent.py` or the `/api/v1/agents/{name}/run` endpoint. Call fails with `KeyError: Agent 'X' not found in registry`.  
**Agents affected:** competitor_discovery, pipeline_orchestrator, ai_assistant, twitter_agent, newsletter_agent, video_scriptwriter, lead_magnet_agent, strategy_synthesizer, auto_mode_engine, broll_selector  
**Fix applied (2026-05-06):** Added 10 missing module paths to `import_all_agents()` in `core/agent_registry.py`. Registry now shows 34/34 agents.

### INFRA-02 — 14 tables missing (asyncpg multi-statement bug) ✅ RESOLVED

**Severity:** High  
**Impact:** `alembic upgrade head` failed with `asyncpg.exceptions.PostgresSyntaxError: cannot insert multiple commands into a prepared statement`. 10 migration files had `ALTER TABLE ... ENABLE ROW LEVEL SECURITY; CREATE POLICY ...` combined in a single `op.execute()` call, which asyncpg rejects.  
**Fix applied (2026-05-06):** Split every multi-statement `op.execute()` into two separate calls across all 10 migration files. `alembic upgrade head` now completes cleanly — 33 tables present, head == `a3b4c5d6e7f8`.  
**Root cause documented in:** ISSUES_AND_FIXES.md Issue 36.

### INFRA-03 — Celery worker has no healthcheck in docker-compose ✅ RESOLVED

**Severity:** Medium  
**Impact:** If the worker crashes and restarts in a loop, `docker compose ps` still shows `Up`. Tasks appear dispatched but never execute. Silent failure in pipeline_orchestrator and auto_mode_engine.  
**Fix applied (2026-05-06):** Added healthcheck to worker service in `docker-compose.yml` using `celery inspect ping`. Takes effect on next `docker compose up` or container restart.

---

## Phase 0 Sign-Off Checklist

Before moving to Phase 1 (brand_voice_keeper):

- [x] All 4 containers healthy / up — api, db, redis healthy; worker up
- [x] `curl http://localhost:8000/health` → `{"status":"ok"}`
- [x] 30 API routes registered
- [x] `alembic current` == `alembic heads` — both `a3b4c5d6e7f8`
- [x] 33 tables present — all previously missing tables now created
- [ ] RLS functional test passes (org B sees 0 rows from org A's keywords) — run manually before Phase 1
- [x] 34 agents in registry — all agents discoverable
- [x] All 5 critical env vars SET
- [ ] Prompts seeded for agents under test — verify per-agent before each Phase
- [ ] Worker logs clean — run `docker logs --tail 30 vikas-worker-1` before Phase 1

**Phase 0 signed off: ready to proceed to Phase 1 (brand_voice_keeper)**
