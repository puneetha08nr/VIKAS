# Claude Code Setup Guide — Vikas Platform

## Before You Start

### Prerequisites (do these manually, once)

```bash
# 1. Install Node.js 18+
node --version   # must be 18+

# 2. Install Claude Code
npm install -g @anthropic-ai/claude-code

# 3. Install Python 3.12
python3 --version  # must be 3.12+

# 4. Install uv (Python package manager, faster than pip)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 5. Install Docker Desktop
# Download from https://www.docker.com/products/docker-desktop
docker --version  # verify

# 6. Verify Claude Code works
claude --version
```

---

## Step 1 — Create the repo and launch Claude Code

```bash
mkdir vikas
cd vikas
git init
claude
```

Claude Code is now running inside your project. Every prompt below is typed into Claude Code's terminal interface.

---

## Step 2 — Scaffold the monorepo

Paste this prompt into Claude Code exactly:

```
Create a monorepo for a project called vikas with this structure:

apps/
  web/     - Next.js 14 app (App Router, TypeScript, Tailwind, shadcn/ui)
  api/     - FastAPI Python backend

packages/
  shared-types/  - TypeScript shared types

infra/
  docker/       - Dockerfiles and docker-compose
  terraform/    - empty for now

tests/
  unit/
  integration/
  golden_traces/

scripts/   - empty Python scripts folder

Create:
- turbo.json for Turborepo
- pyproject.toml for Python workspace using uv
- .gitignore covering Python, Node, Docker, .env files
- README.md with project name and one-line description

Do not install any packages yet. Just create the folder structure and config files.
```

**Verify:**
```bash
ls apps/ packages/ infra/ tests/ scripts/
cat turbo.json
```

---

## Step 3 — Docker Compose local dev stack

Paste into Claude Code:

```
Create infra/docker/docker-compose.yml that runs:

1. PostgreSQL 16 with pgvector extension
   - port 5432
   - db: vikas, user: vikas, password: vikas_dev
   - health check: pg_isready

2. Redis 7
   - port 6379
   - health check: redis-cli ping

3. FastAPI backend (apps/api)
   - port 8000
   - hot reload with uvicorn --reload
   - depends on postgres and redis being healthy
   - mounts ./apps/api as volume

4. Celery worker (same apps/api codebase)
   - runs: celery -A workers.celery_app worker --loglevel=info
   - depends on postgres and redis
   - mounts ./apps/api as volume

5. Next.js frontend (apps/web)
   - port 3000
   - hot reload
   - depends on api

Also create infra/docker/Dockerfile.api and infra/docker/Dockerfile.web.

Add a .env.example at the project root with all required environment variables.
```

**Verify:**
```bash
docker compose -f infra/docker/docker-compose.yml up -d
docker compose -f infra/docker/docker-compose.yml ps
# all 5 services should show healthy or running
```

---

## Step 4 — FastAPI skeleton

Paste into Claude Code:

```
Set up the FastAPI application in apps/api/ with this structure:

apps/api/
  main.py              - FastAPI app, CORS, lifespan, router includes
  config/
    settings.py        - pydantic-settings: reads from .env, all config here
    model_tiers.yaml   - LLM tier config (see below)
  core/                - empty __init__.py files only, we fill these next
  db/
    models/            - empty
    migrations/        - Alembic setup
    session.py         - async session factory stub
  agents/
    seo/
    content/
    competitor/
    video/
    knowledge/
    orchestration/
  integrations/        - empty
  rag/                 - empty
  preferences/         - empty
  api/
    v1/
      __init__.py
      router.py        - includes all v1 routes
  workers/
    celery_app.py      - Celery instance config pointing to Redis

model_tiers.yaml content:
tiers:
  fast:
    primary: {provider: openai, model: gpt-4o-mini}
    fallback:
      - {provider: anthropic, model: claude-haiku-4-5-20251001}
    max_tokens: 4096
    temperature: 0.3
  standard:
    primary: {provider: anthropic, model: claude-sonnet-4-6}
    fallback:
      - {provider: openai, model: gpt-4o}
    max_tokens: 8192
    temperature: 0.7
  advanced:
    primary: {provider: anthropic, model: claude-opus-4-6}
    fallback:
      - {provider: openai, model: o1}
    max_tokens: 16384
    temperature: 0.9

cost_limits:
  per_org_daily_usd: 50.0
  per_agent_run_usd: 5.0
  kill_on_breach: true

Install dependencies: fastapi, uvicorn, pydantic, pydantic-settings, sqlalchemy,
asyncpg, alembic, celery, redis, litellm, httpx, python-dotenv, pyyaml

Use uv for dependency management. Create pyproject.toml with all deps.
```

**Verify:**
```bash
cd apps/api
uv run uvicorn main:app --reload
# should start on port 8000
# open http://localhost:8000/docs
```

---

## Step 5 — Database schema + RLS

Paste into Claude Code:

```
Create the complete database schema for the vikas platform.

In apps/api/db/models/ create one file per domain:

organizations.py — id (uuid pk), name, slug (unique), settings (jsonb), created_at, updated_at

keywords.py — id, org_id (fk→orgs, rls), keyword, volume (int), kd (float), cpc (float),
  cluster_id (fk→keyword_clusters nullable), status (enum: raw|validated|clustered|archived),
  source_agent (str), created_at, updated_at

keyword_clusters.py — id, org_id, name, intent (enum: informational|navigational|commercial|transactional),
  primary_keyword_id (fk→keywords nullable), created_at

opportunities.py — id, org_id, keyword_id (fk), source (str), search_score (float),
  competitive_gap_score (float), trend_score (float), engagement_score (float),
  composite_score (float), status (enum: new|in_progress|done|archived),
  format_fit_scores (jsonb), created_at

content_items.py — id, org_id, opportunity_id (fk nullable), format
  (enum: article|linkedin|twitter|newsletter|video_script|lead_magnet),
  title (str), body (text), status (enum: draft|review|approved|published|rejected),
  brand_voice_score (float nullable), seo_score (float nullable),
  published_url (str nullable), created_at, updated_at

content_reviews.py — id, org_id, content_item_id (fk), dimension (str),
  score (float), feedback_text (text nullable), reviewer (str), created_at

competitors.py — id, org_id, domain (str), last_crawled_at (timestamptz nullable), created_at

competitor_content.py — id, org_id, competitor_id (fk), url (str), title (str),
  word_count (int), threat_score (float nullable), keywords_overlap (jsonb), created_at

trend_signals.py — id, org_id, source (str), query (str), momentum (float), detected_at

knowledge_chunks.py — id, org_id, source_doc (str), chunk_text (text),
  embedding (Vector(1536)), metadata (jsonb), created_at

brand_voice.py — id, org_id (unique), tone (str), vocabulary (jsonb),
  banned_phrases (jsonb), style_rules (jsonb), updated_at

preferences.py — id, org_id, pattern (text), weight (float),
  source (enum: approve|edit|reject), extracted_at

prompts.py — id, agent_name (str), version (int), template (text),
  active (bool default false), created_at

agent_runs.py — id, org_id, agent_name (str), status (enum: running|success|failed|partial),
  duration_ms (int nullable), tokens_in (int default 0), tokens_out (int default 0),
  cost_usd (float default 0), model_used (str nullable), error (text nullable),
  started_at, completed_at

pipeline_runs.py — id, org_id, pipeline_name (str), status (enum: running|success|failed|partial),
  started_at, completed_at

Also create db/models/__init__.py that imports all models.

Then create the Alembic migration:
1. alembic init db/migrations
2. Configure alembic.ini to use DATABASE_URL from env
3. Create initial migration: alembic revision --autogenerate -m "initial schema"

After models, create db/session.py:
- async engine using asyncpg
- async session factory
- context manager that sets app.current_org_id at session start:
  await session.execute(text(f"SET app.current_org_id = '{org_id}'"))
- dependency function get_db(org_id) for FastAPI route injection

Finally, write raw SQL for RLS policies on every table:
  ALTER TABLE keywords ENABLE ROW LEVEL SECURITY;
  CREATE POLICY org_isolation ON keywords
    USING (org_id = current_setting('app.current_org_id')::uuid);
(repeat for all org-scoped tables)

Put the RLS SQL in db/migrations/rls_policies.sql
```

**Verify:**
```bash
cd apps/api
uv run alembic upgrade head
# should run without errors

# Test RLS manually:
docker exec -it vikas_postgres psql -U vikas -d vikas -c "
  SET app.current_org_id = '00000000-0000-0000-0000-000000000001';
  SELECT * FROM keywords;
"
# should return empty, not error
```

---

## Step 6 — BaseAgent + LLMRouter

Paste into Claude Code:

```
Create the core agent framework in apps/api/core/

1. apps/api/core/agent_base.py

Create these Pydantic models:
- AgentContext: org_id (str), run_id (str), params (dict), config (dict)
- AgentResult: status (str), data (dict), tokens_used (int), cost_usd (float), duration_ms (int), error (str | None)
- PreflightResult: ok (bool), reason (str | None)

Create BaseAgent (ABC):
- class attributes: name (str), tier (str), version (str = "1.0.0")
- run(ctx) -> AgentResult: async, DO NOT OVERRIDE
  - calls preflight, execute, _audit, _notify
  - wraps in try/except, logs failure to agent_runs
  - tracks wall-clock duration
- preflight(ctx) -> PreflightResult: base checks quota + required params, subclass can extend
- execute(ctx) -> AgentResult: abstractmethod, subclasses implement this only
- call_llm(ctx, prompt, **kwargs) -> str: calls LLMRouter using self.tier
- _audit(ctx, result): writes to agent_runs table
- _notify(ctx, result): logs warning on failure (Slack/email hook placeholder)

2. apps/api/core/llm_router.py

LLMRouter class:
- loads model_tiers.yaml on init
- complete(prompt, tier, org_id, **kwargs) -> str:
  - checks org daily cost against limit in DB
  - calls primary provider via litellm.acompletion
  - on failure: tries each fallback in order
  - if all fail: raises LLMUnavailableError
  - always records tokens in/out and cost_usd
- get_cost(model, tokens_in, tokens_out) -> float: uses litellm.completion_cost

3. apps/api/core/cost_tracker.py

CostTracker class:
- async add(org_id, run_id, model, tokens_in, tokens_out, cost_usd, db)
- async get_daily_total(org_id, db) -> float
- async check_limit(org_id, daily_limit_usd, db) -> bool

4. apps/api/core/task_queue.py

- AgentCommand: Pydantic model: agent_name, org_id, run_id (uuid), params (dict), created_at
- dispatch(command: AgentCommand) -> str: serializes and sends to Celery queue
- Celery task: execute_agent(command_dict) that deserializes, looks up agent in registry, runs it

5. apps/api/core/agent_registry.py

- REGISTRY: dict mapping agent_name -> agent class
- register(cls): decorator that adds to REGISTRY
- get(name) -> BaseAgent instance
- list_agents() -> list[str]

Write unit tests in tests/unit/core/:
- test_base_agent.py: FakeAgent that returns success, verify agent_runs record created, cost logged
- test_llm_router.py: mock litellm, verify fallback fires on primary failure
- test_cost_tracker.py: verify daily total accumulates correctly

Use pytest + pytest-asyncio. Mock the DB with pytest fixtures.
```

**Verify:**
```bash
cd apps/api
uv run pytest ../../tests/unit/core/ -v      

or 
uv run pytest tests/unit/core/-v                                                                                                                     # all tests must pass before proceeding
```

---

## Step 7 — BaseIntegration

Paste into Claude Code:

```
Create apps/api/integrations/base.py

BaseIntegration class using httpx.AsyncClient:

Properties:
- base_url (str)
- name (str)
- credentials loaded from org settings in DB

Methods:
- async request(method, path, **kwargs) -> dict
  Wraps httpx with:
  1. Retry: 3 attempts, exponential backoff (1s, 2s, 4s), retry on 429/500/502/503
  2. Rate limiting: token bucket, max_requests_per_minute configurable per subclass
  3. Circuit breaker: after 5 consecutive failures, open circuit for 60s,
     raise CircuitOpenError without attempting request
  4. Structured error logging: logs method, url, status_code, response_time_ms
  5. On all failures: raises IntegrationError with context

- async health_check() -> bool: GET /health or equivalent, returns True/False
- async get_credentials(org_id, db) -> dict: fetch from org settings, never hardcode

Create custom exceptions:
- IntegrationError(message, status_code, integration_name)
- CircuitOpenError(integration_name, retry_after_seconds)
- RateLimitError(integration_name, retry_after_seconds)

Then create apps/api/integrations/google_search_console.py as the first real adapter:

GoogleSearchConsoleIntegration(BaseIntegration):
- authenticate with service account JSON (from org credentials)
- async get_search_analytics(site_url, start_date, end_date, dimensions) -> list[dict]
- async get_sitemaps(site_url) -> list[str]
- async list_sites() -> list[str]

Write tests/unit/integrations/test_base_integration.py:
- test retry fires on 500
- test circuit breaker opens after 5 failures
- test circuit breaker rejects requests while open
Mock httpx with respx.
```

**Verify:**
```bash
uv run pytest tests/unit/integrations/ -v
```

---

## Step 8 — Prompt Registry

Paste into Claude Code:

```
Create apps/api/core/prompt_registry.py

PromptRegistry class:
- async get(agent_name, db) -> str
  SELECT template FROM prompts WHERE agent_name = $1 AND active = true
  Raise PromptNotFoundError if missing — never fall back to hardcoded strings

- async set(agent_name, template, db) -> int (new version number)
  Deactivates current active prompt for agent_name
  Inserts new row with version = max(version) + 1, active = true
  Returns new version number

- async rollback(agent_name, version, db) -> bool
  Deactivates current, activates specified version

- async history(agent_name, db) -> list[dict]
  Returns all versions for an agent ordered by version desc

Create a seed script scripts/seed_prompts.py:
Seeds the prompts table with starter prompts for:
- keyword_research: "You are a keyword research specialist..."
- keyword_validator: "You are validating keyword metrics..."
- article_planner: "You are creating a detailed article outline..."
- article_writer: "You are writing a high-quality SEO article..."
- linkedin_agent: "You are writing a LinkedIn post..."
- brand_voice_keeper: "You are enforcing brand voice guidelines..."

Each prompt should be a real, usable starter — not lorem ipsum.
Add org_id awareness: prompts are global (no org_id) — brand voice adjustments
are injected at runtime by the preference system, not stored as separate prompts.

Write tests/unit/core/test_prompt_registry.py:
- test get returns active prompt
- test set deactivates old, creates new
- test rollback switches active version
- test get raises PromptNotFoundError when missing
```

**Verify:**
```bash
uv run pytest tests/unit/core/test_prompt_registry.py -v
python scripts/seed_prompts.py
# check prompts table has entries
```

---

## Step 9 — RAG Pipeline

Paste into Claude Code:

```
Create the RAG pipeline in apps/api/rag/

1. apps/api/rag/chunker.py

TextChunker class:
- chunk(text, source_doc, strategy="fixed") -> list[dict]
- Fixed strategy: 512 tokens per chunk, 50 token overlap
- Each chunk dict: {text, source_doc, chunk_index, metadata}
- Use tiktoken for token counting (cl100k_base encoding)

2. apps/api/rag/embeddings.py

EmbeddingGenerator class:
- async generate(texts: list[str]) -> list[list[float]]
  Calls OpenAI text-embedding-3-small (1536 dims)
  Batches in groups of 100 to avoid rate limits
- async generate_one(text: str) -> list[float]

3. apps/api/rag/retriever.py

RAGRetriever class:
- async search(query, org_id, db, top_k=5) -> list[dict]
  1. Generate query embedding
  2. pgvector cosine similarity search scoped to org_id:
     SELECT chunk_text, source_doc, metadata,
       1 - (embedding <=> $1::vector) AS similarity
     FROM knowledge_chunks
     WHERE org_id = current_setting('app.current_org_id')::uuid
     ORDER BY embedding <=> $1::vector
     LIMIT $2
  3. Return chunks with similarity scores

4. apps/api/rag/brand_voice.py

BrandVoiceLoader class:
- async load(org_id, db) -> dict
  Returns brand_voice row as dict (tone, vocabulary, banned_phrases, style_rules)
- async format_for_prompt(org_id, db) -> str
  Formats brand voice as a prompt section:
  "Tone: {tone}. Avoid: {banned_phrases}. Style: {style_rules}"

Write tests/unit/rag/:
- test_chunker.py: verify chunk count, overlap, token sizes
- test_retriever.py: mock pgvector query, verify result format
Mock embeddings API with pytest fixtures returning random vectors.
```

**Verify:**
```bash
uv run pytest tests/unit/rag/ -v
```

---

## Step 10 — First Agent: keyword_research

Paste into Claude Code:

```
Create the first real agent: apps/api/agents/seo/keyword_research.py

@register
class KeywordResearchAgent(BaseAgent):
    name = "keyword_research"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        seed = ctx.params["seed_keyword"]
        org_id = ctx.org_id

        # 1. Load prompt from registry
        prompt_template = await PromptRegistry().get("keyword_research", ctx.db)

        # 2. Load brand voice for context
        brand_voice = await BrandVoiceLoader().format_for_prompt(org_id, ctx.db)

        # 3. Build prompt: inject seed + brand voice
        prompt = f"{prompt_template}\n\nBrand context:\n{brand_voice}\n\nSeed keyword: {seed}"

        # 4. Call LLM, expect JSON back
        response = await self.call_llm(ctx, prompt)

        # 5. Parse response — expect list of keyword objects
        keywords = parse_keyword_json(response)  # helper that safely parses

        # 6. Write to DB (all scoped to org_id via RLS session)
        await save_keywords(keywords, org_id, agent_name=self.name, db=ctx.db)

        return AgentResult(
            status="success",
            data={"keywords_found": len(keywords), "seed": seed},
            tokens_used=ctx.llm.last_tokens_used,
            cost_usd=ctx.llm.last_cost_usd,
            duration_ms=0  # filled by BaseAgent.run()
        )

Also create scripts/run_agent.py CLI:
  python scripts/run_agent.py --agent keyword_research --params '{"seed_keyword": "ai marketing"}' --org <org_id>

This script:
1. Loads .env
2. Creates DB session with org_id
3. Instantiates agent via registry
4. Calls agent.run(ctx)
5. Prints result as formatted JSON

Write tests/unit/agents/seo/test_keyword_research.py:
- mock LLM to return valid JSON keyword list
- verify keywords written to DB
- verify agent_run record created with cost > 0
- verify PromptNotFoundError raised if no prompt seeded

Write tests/golden_traces/keyword_research_trace.json:
Store: {input_params, mock_llm_response, expected_db_records, expected_result_status}
```


**Done when this command works cleanly:**
```bash
python scripts/run_agent.py \
  --agent keyword_research \
  --params '{"seed_keyword": "ai marketing"}' \
  --org 00000000-0000-0000-0000-000000000001

# Expected output:
# {
#   "status": "success",
#   "data": {"keywords_found": 25, "seed": "ai marketing"},
#   "cost_usd": 0.0003,
#   "duration_ms": 1842
# }
```

---

## Step 11 — Next.js + Auth scaffold

Paste into Claude Code:

```
Set up the Next.js 14 frontend in apps/web/

1. Install: next, typescript, tailwindcss, shadcn-ui, @tanstack/react-query,
   zod, axios, @supabase/supabase-js, lucide-react

2. Create app structure:
   app/
     (auth)/
       login/page.tsx       - email/password login form
       signup/page.tsx      - signup + org name form
     (dashboard)/
       layout.tsx           - sidebar nav + auth guard
       page.tsx             - redirect to /keywords
       keywords/page.tsx    - empty shell with heading
       content/page.tsx     - empty shell
       knowledge/page.tsx   - empty shell
       settings/page.tsx    - API keys form (fields: OpenAI key, Anthropic key,
                              WordPress URL, WordPress app password, GSC service account)

3. Sidebar nav component: links to all 4 pages, shows org name, logout button

4. Auth guard in dashboard layout: redirect to /login if no session

5. API client: lib/api.ts
   - axios instance pointing to NEXT_PUBLIC_API_URL
   - interceptor that adds Authorization header from Supabase session
   - typed functions: triggerAgent(agentName, params), getAgentRun(runId)

6. Use Supabase Auth (PKCE flow):
   - NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY from env
   - On signup: create Supabase user, then POST /api/v1/orgs to create org in DB
   - Store org_id in Supabase user metadata

Keep all pages as shells for now — no real data, just layout and navigation working.
```

**Verify:**
```bash
cd apps/web
npm run dev
# open http://localhost:3000
# signup flow should work and land on dashboard shell
```

---

## Step 12 — Auth API endpoint + org creation

Paste into Claude Code:

```
Create the org and auth endpoints in apps/api/api/v1/

1. apps/api/api/v1/orgs.py

POST /api/v1/orgs
  Body: {name: str, slug: str, supabase_user_id: str}
  - Verify Supabase JWT from Authorization header
  - Create organization record in DB
  - Seed brand_voice row with defaults for the org
  - Return {org_id, name, slug}

GET /api/v1/orgs/me
  - From JWT, return current org details

PUT /api/v1/orgs/me/settings
  Body: {openai_api_key?, anthropic_api_key?, wordpress_url?, ...}
  - Encrypt API keys before storing in org settings jsonb
  - Use Fernet symmetric encryption, key from SETTINGS_ENCRYPTION_KEY env var
  - Never return raw keys — only return masked versions (sk-...xxxx)

2. apps/api/api/deps.py

- get_current_org(token: JWT) -> Organization: verify Supabase JWT, return org
- get_db_for_org(org: Organization) -> AsyncSession: session with RLS context set

These two deps are used by every protected route.

3. apps/api/api/v1/agents.py

POST /api/v1/agents/{agent_name}/run
  Body: {params: dict}
  - Validate agent_name exists in registry
  - Create agent_run record with status=running
  - Dispatch AgentCommand to Celery queue
  - Return {run_id} immediately (async — don't wait for completion)

GET /api/v1/agents/runs/{run_id}
  - Return agent_run record (status, cost, duration, error)

GET /api/v1/agents/runs
  - Return last 50 agent runs for org, ordered by started_at desc
```

**Verify:**
```bash
# hit the API from curl:
curl -X POST http://localhost:8000/api/v1/orgs \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Org", "slug": "test-org", "supabase_user_id": "test-123"}'

curl -X POST http://localhost:8000/api/v1/agents/keyword_research/run \
  -H "Authorization: Bearer <jwt>" \
  -d '{"params": {"seed_keyword": "ai marketing"}}'
# returns {run_id: "..."}

curl http://localhost:8000/api/v1/agents/runs/<run_id>
# returns {status: "success", cost_usd: 0.0003, ...}
```

---

## Step 13 — Integration test: full pipeline

Paste into Claude Code:

```
Create tests/integration/test_keyword_pipeline.py

This is the end-to-end integration test for v1 phase 1.
Use a real test PostgreSQL DB (separate from dev DB, created in CI).
Mock only external API calls (GSC, OpenAI) — everything else is real.

Test: test_keyword_research_end_to_end
1. Create test org in DB
2. Seed brand voice
3. Seed keyword_research prompt
4. Mock OpenAI to return valid keyword JSON
5. Run keyword_research agent via CLI command (subprocess)
6. Assert: keywords written to DB under correct org_id
7. Assert: agent_run record exists with status=success, cost_usd > 0
8. Assert: running same test with different org_id returns zero rows from first org (RLS test)

Test: test_rls_isolation
1. Create org_a and org_b
2. Insert keywords for org_a
3. Create DB session scoped to org_b
4. SELECT * FROM keywords must return 0 rows
5. This test failing = critical security regression, blocks all merges

Add to CI (create .github/workflows/ci.yml):
- trigger: push to any branch, PR to main
- jobs:
  1. lint: ruff check apps/api
  2. typecheck: pyright apps/api
  3. unit-tests: pytest tests/unit/ --cov
  4. integration-tests: pytest tests/integration/ (uses docker compose services)
- All 4 jobs must pass to merge
```

**Verify:**
```bash
uv run pytest tests/integration/ -v
# test_rls_isolation MUST pass — this is non-negotiable
```

---

## Step 14 — Remaining 11 v1 agents

Once steps 1–13 are verified, paste this into Claude Code **one agent at a time:**

```
Create apps/api/agents/seo/keyword_validator.py

KeywordValidatorAgent(BaseAgent):
  name = "keyword_validator"
  tier = "fast"

  execute(ctx):
    - Input: ctx.params["keyword_ids"] — list of keyword UUIDs
    - Fetch keywords from DB by ids
    - For each keyword batch (50 at a time):
      - Call LLM with keyword list, ask to assess search intent and commercial value
      - Update keyword.status = "validated" in DB
      - Update kd, volume estimates based on LLM assessment
        (note: real volume data comes from SEO integration — LLM is fallback)
    - Return count of validated keywords

Also seed a prompt for keyword_validator in the prompts table.
Write unit test with mocked LLM.
```

Repeat this pattern for each agent in this order:
1. keyword_validator
2. gap_analyzer
3. rank_tracker
4. document_ingester (uses chunker + embeddings from RAG pipeline)
5. brand_voice_keeper
6. rag_searcher
7. article_planner (uses RAG retriever for brand voice + past content)
8. article_writer (uses RAG retriever, brand voice, preferences injection)
9. content_director (orchestrator: dispatches article_planner → article_writer → linkedin_agent)
10. linkedin_agent
11. wordpress_publisher (uses WordPress integration via BaseIntegration)

**Do not batch agents.** One at a time, tests passing before the next one starts.

---

## Step 15 — Wire content review queue in dashboard

Paste into Claude Code:

```
Build the content review queue page at apps/web/app/(dashboard)/content/page.tsx

Data:
- GET /api/v1/content — lists content_items for org with status=draft|review
- PATCH /api/v1/content/{id}/approve — sets status=approved, stores empty feedback
- PATCH /api/v1/content/{id}/reject — sets status=rejected, requires feedback_text
- PATCH /api/v1/content/{id}/edit — updates body, sets status=review, stores edit feedback

UI components:
- ContentCard: shows title, format badge, word count, brand_voice_score, seo_score
- ContentBody: renders markdown body with edit mode toggle
- ReviewActions: Approve / Edit / Reject buttons
- FeedbackModal: textarea for reject reason or edit notes, required before submitting

When user approves: store {source: "approve"} in preferences table
When user edits: store {source: "edit", pattern: diff summary} in preferences table
When user rejects: store {source: "reject", pattern: reason} in preferences table

This feedback storage is the foundation of the preference learning loop.

Also add these API endpoints in apps/api/api/v1/content.py:
GET /api/v1/content
PATCH /api/v1/content/{id}/approve
PATCH /api/v1/content/{id}/reject
PATCH /api/v1/content/{id}/edit
```

---

## Final Verification — v1 Acceptance Test

Run this manually after all steps complete:

```bash
# 1. Start full stack
docker compose -f infra/docker/docker-compose.yml up -d

# 2. Open http://localhost:3000
# 3. Sign up as new user, create org "Test Marketing Co"
# 4. Go to Settings, enter OpenAI API key

# 5. Trigger keyword research via API
curl -X POST http://localhost:8000/api/v1/agents/keyword_research/run \
  -H "Authorization: Bearer <your_jwt>" \
  -d '{"params": {"seed_keyword": "ai marketing tools"}}'

# 6. Poll until complete
curl http://localhost:8000/api/v1/agents/runs/<run_id>

# 7. Trigger content_director on first opportunity
curl -X POST http://localhost:8000/api/v1/agents/content_director/run \
  -H "Authorization: Bearer <your_jwt>" \
  -d '{"params": {"opportunity_id": "<first_opportunity_id>"}}'

# 8. Open http://localhost:3000/content
# — drafts should appear in review queue

# 9. Approve an article
# 10. Trigger wordpress_publisher
curl -X PATCH http://localhost:8000/api/v1/content/<id>/approve

# v1 DONE: seed keyword → published WordPress post, full trail in DB
```

---

## Notes for the Team

- **Never skip a verification step.** Each step's output is the next step's input.
- **One agent at a time in step 14.** Batching agents before tests pass creates compounding bugs.
- **RLS test failure blocks everything.** It's in CI for this reason.
- **All prompts go through the registry.** No exceptions, no hardcoded strings.
- **CLAUDE.md is the source of truth.** Update it whenever a design decision changes.
