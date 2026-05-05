# CLAUDE.md — Vikas AI Marketing Platform

## What This Project Is

A multi-agent AI platform that automates the entire marketing operation: keyword research → content creation → review → publishing → performance tracking. 45+ specialized AI agents collaborate through a shared PostgreSQL database layer. Agents are stateless, communicate via shared state (not direct calls), and run autonomously on nightly schedules.

This is NOT a chatbot. It's a marketing backend that runs while you sleep.

---

## Architecture Overview

**Three layers:**
- **Presentation**: Next.js 14 dashboard + AI chat interface
- **Agent layer**: Python FastAPI backend with 45+ agents across 6 departments
- **Data + Integration layer**: PostgreSQL (pgvector), Redis queue, 13+ external integrations

**Agent departments:**
- SEO Intelligence (8 agents): keyword research, validation, gap analysis, rank tracking, trends, AEO, site audit, topic discovery
- Content Production (9 agents): director orchestrator, article planner, article writer, LinkedIn, Twitter/X, newsletter, video script, lead magnet, image creator
- Competitor Intel (5 agents): sitemap monitor, content extractor, keyword overlap, threat scorer, competitor discovery
- Video Production (4 agents): script generator, b-roll selector, video producer, thumbnail generator
- Knowledge & Ops (7 agents): document ingester, brand voice keeper, RAG searcher, internal link finder, WordPress publisher, pipeline orchestrator, AI assistant
- Orchestration (4 agents): auto mode engine, content director, opportunity scorer, strategy synthesizer

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 (App Router, RSC), TypeScript, shadcn/ui, TanStack Query |
| API | FastAPI, Python 3.12, Pydantic v2, async/await throughout |
| Agents | Custom Python framework — no LangChain/CrewAI dependency |
| LLM routing | LiteLLM (or custom router) — OpenAI, Anthropic, Google, OpenRouter |
| Database | PostgreSQL 16 + pgvector extension, Alembic migrations |
| Queue | Redis + Celery (or ARQ) for async agent execution |
| Storage | S3/GCS for media (images, videos, documents) |
| Auth | Supabase Auth or Clerk — org-based multi-tenancy |
| Infra | Docker Compose (dev), Terraform (prod), GitHub Actions CI/CD |
| Monitoring | OpenTelemetry → Grafana + Loki |

---

## Project Structure

```
vikas/
├── apps/
│   ├── web/                        # Next.js 14 dashboard
│   │   ├── app/
│   │   │   ├── (auth)/
│   │   │   ├── (dashboard)/
│   │   │   │   ├── keywords/
│   │   │   │   ├── content/
│   │   │   │   ├── competitors/
│   │   │   │   ├── video/
│   │   │   │   ├── analytics/
│   │   │   │   ├── knowledge/
│   │   │   │   ├── auto-mode/
│   │   │   │   ├── settings/
│   │   │   │   └── chat/
│   │   │   └── api/                # BFF routes
│   │   └── components/
│   │       ├── ui/                 # shadcn primitives
│   │       └── domain/             # business components
│   │
│   └── api/                        # FastAPI backend
│       ├── main.py
│       ├── config/
│       │   ├── settings.py         # pydantic-settings, env-based
│       │   └── model_tiers.py      # fast/standard/advanced LLM config
│       ├── core/
│       │   ├── agent_base.py       # BaseAgent ABC
│       │   ├── agent_registry.py   # discover + instantiate agents by name
│       │   ├── contracts.py        # Pydantic output contracts for all agents
│       │   ├── llm_router.py       # model selection + fallback
│       │   ├── cost_tracker.py     # token usage aggregation
│       │   ├── task_queue.py       # Celery/ARQ dispatch
│       │   └── notifications.py    # Slack/email alerts
│       ├── db/
│       │   ├── models/             # SQLAlchemy ORM models
│       │   ├── migrations/         # Alembic
│       │   └── session.py          # async session + RLS context manager
│       ├── agents/
│       │   ├── seo/                # 8 agents
│       │   ├── content/            # 9 agents
│       │   ├── competitor/         # 5 agents
│       │   ├── video/              # 4 agents
│       │   ├── knowledge/          # 7 agents
│       │   └── orchestration/      # 4 agents
│       ├── integrations/           # 13+ external service adapters
│       ├── rag/                    # embeddings, chunker, retriever, brand voice
│       ├── preferences/            # feedback store, learner, prompt injection
│       ├── api/v1/                 # FastAPI route modules
│       └── workers/                # scheduler, nightly pipeline, event handlers
│
├── packages/
│   ├── shared-types/               # TS types shared across apps
│   └── agent-sdk/                  # agent protocol, test utilities
│
├── infra/
│   ├── docker/
│   │   ├── Dockerfile.api
│   │   ├── Dockerfile.web
│   │   ├── Dockerfile.worker
│   │   └── docker-compose.yml
│   └── terraform/
│
├── tests/
│   ├── unit/agents/
│   ├── integration/pipelines/
│   └── golden_traces/              # regression: expected agent outputs
│
├── scripts/
│   ├── seed_db.py
│   ├── run_agent.py                # CLI to run any agent standalone
│   └── benchmark_models.py
│
├── turbo.json
├── pyproject.toml
└── CLAUDE.md                       # this file
```

---

## Core Design Principles

1. **Agents share state through the database, never direct calls.** Agent A writes a keyword to the DB. Agent B reads it later. They don't know about each other. This makes every agent independently replaceable and testable.

2. **Every agent inherits from BaseAgent.** The base class provides: preflight validation, LLM model routing, token cost tracking, audit logging (duration, cost, status, error), async execution, retry with exponential backoff, and team notifications. New agents only implement `execute()`.

3. **Row-level security (RLS) for multi-tenancy.** Every DB query is automatically scoped to the current org. This is enforced at the PostgreSQL session level using `SET app.current_org_id`, not application-level WHERE clauses. Test RLS in CI.

4. **Three-tier LLM routing.** Fast tier (GPT-4o-mini, Haiku, Gemini Flash) handles 60-80% of runs — data collection, filtering, validation. Standard tier (GPT-4o, Sonnet, Gemini Pro) handles content writing. Advanced tier (Opus, o1) is rare, for strategy synthesis only. Each agent declares its tier in config. Router picks cheapest available provider with automatic fallback.

5. **Preference learning loop.** Human approves/edits/rejects content → feedback stored → patterns extracted weekly → preferences injected into future agent prompts. This is how the system gets smarter over time.

6. **Nothing auto-publishes without human approval.** Auto Mode drafts go to review queue. Humans approve. This is a hard constraint, not a setting.

---

## Database Schema — Core Tables

```sql
-- All tables have: id (uuid), org_id (uuid, RLS), created_at, updated_at

-- Tenant root
organizations (id, name, slug, settings_jsonb)

-- SEO
keywords (id, org_id, keyword, volume, kd, cpc, cluster_id, status, source_agent)
keyword_clusters (id, org_id, name, intent, primary_keyword_id)

-- Opportunities
opportunities (id, org_id, keyword_id, source, search_score, competitive_gap_score, trend_score, engagement_score, composite_score, status, format_fit_scores_jsonb)

-- Content
content_items (id, org_id, opportunity_id, format, title, body, status[draft|review|approved|published], brand_voice_score, seo_score, published_url)
content_reviews (id, org_id, content_item_id, dimension, score, feedback_text, reviewer)

-- Competitors
competitors (id, org_id, domain, last_crawled_at)
competitor_content (id, org_id, competitor_id, url, title, word_count, threat_score, keywords_overlap)

-- Trends
trend_signals (id, org_id, source, query, momentum, detected_at)

-- Knowledge / RAG
knowledge_chunks (id, org_id, source_doc, chunk_text, embedding vector(1536), metadata_jsonb)
brand_voice (id, org_id, tone, vocabulary, banned_phrases, style_rules_jsonb)

-- Preferences
preferences (id, org_id, pattern, weight, source[approve|edit|reject], extracted_at)

-- Operations
agent_runs (id, org_id, agent_name, status, duration_ms, tokens_in, tokens_out, cost_usd, model_used, error, started_at)
pipeline_runs (id, org_id, pipeline_name, status, agent_run_ids[], started_at, completed_at)
```

---

## BaseAgent Contract

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel

class AgentContext(BaseModel):
    org_id: str
    run_id: str
    params: dict  # agent-specific input
    db: AsyncSession  # RLS-scoped
    llm: LLMRouter
    config: AgentConfig

class AgentResult(BaseModel):
    status: str  # success | failed | partial
    data: dict
    tokens_used: int
    cost_usd: float
    duration_ms: int

class BaseAgent(ABC):
    name: str
    tier: str  # fast | standard | advanced
    version: str

    async def run(self, ctx: AgentContext) -> AgentResult:
        """DO NOT OVERRIDE. Orchestrates the full lifecycle."""
        self.preflight(ctx)          # validate config + quotas
        result = await self.execute(ctx)  # subclass logic
        await self.audit(ctx, result)     # log to agent_runs
        await self.notify(ctx, result)    # alert on failure
        return result

    def preflight(self, ctx: AgentContext) -> None:
        """Check org quotas, required integrations, model availability."""
        pass  # base checks; subclass can extend

    @abstractmethod
    async def execute(self, ctx: AgentContext) -> AgentResult:
        """Implement agent logic here. This is the only method subclasses write."""
        ...

    async def call_llm(self, ctx: AgentContext, prompt: str, **kwargs) -> str:
        """Route to correct model tier, track tokens, handle fallback."""
        return await ctx.llm.complete(
            prompt=prompt, tier=self.tier, org_id=ctx.org_id, **kwargs
        )
```

---

## LLM Router Configuration

```yaml
# config/model_tiers.yaml
tiers:
  fast:
    primary: { provider: openai, model: gpt-4o-mini }
    fallback: [
      { provider: anthropic, model: claude-haiku-4-5-20251001 },
      { provider: google, model: gemini-2.0-flash }
    ]
    max_tokens: 4096
    temperature: 0.3

  standard:
    primary: { provider: anthropic, model: claude-sonnet-4-20250514 }
    fallback: [
      { provider: openai, model: gpt-4o },
      { provider: google, model: gemini-2.0-pro }
    ]
    max_tokens: 8192
    temperature: 0.7

  advanced:
    primary: { provider: anthropic, model: claude-opus-4-20250514 }
    fallback: [
      { provider: openai, model: o1 }
    ]
    max_tokens: 16384
    temperature: 0.9

cost_limits:
  per_org_daily_usd: 50.0
  per_agent_run_usd: 5.0
  kill_on_breach: true
```

---

## Integration Adapter Pattern

Every external service follows this contract:

```python
class BaseIntegration(ABC):
    """All integrations implement this. Handles auth, retry, rate-limit."""

    @abstractmethod
    async def health_check(self) -> bool: ...

    async def request(self, method, url, **kwargs):
        """Wraps httpx with: retry (3x exp backoff), rate-limit (token bucket),
        circuit breaker (5 failures → open 60s), structured error logging."""
        ...
```

Agents never call external APIs directly. They call integration modules. This means swapping from Ahrefs to DataForSEO is one file change.

---

## Key Pipelines

### Keyword → Content (manual trigger)
```
keyword_research.execute(seed) → keywords table
    → keyword_validator.execute(batch) → validated keywords
    → gap_analyzer.execute(keyword) → opportunities table
    → content_director.execute(opportunity) → dispatches to:
        ├── article_planner → article_writer → content_items (draft)
        ├── linkedin_agent → content_items (draft)
        ├── twitter_agent → content_items (draft)
        └── newsletter_agent → content_items (draft)
    → review queue → human approval → wordpress_publisher
```

### Auto Mode (nightly, 2 AM UTC)
```
auto_mode_engine triggers:
    1. trend_collector.execute() → trend_signals
    2. competitor_monitor.execute() → competitor_content
    3. opportunity_scorer.execute() → ranked opportunities
    4. select top N by score + daily caps
    5. inject learned preferences
    6. content_director.execute(each opportunity) → drafts
    7. notify team → morning review queue
```

---

## Eval Framework

Three-tier quality system for every agent. Files live in `tests/evals/<dept>/eval_<agent>.py`.

### Eval types

| Type | Who runs it | When | Purpose |
|---|---|---|---|
| **Structural** | pytest (automated) | Every CI run | Output shape, field types, enum values, DB write confirmed |
| **Relevance** | eval_runner.py | Weekly | LLM-as-judge scores output quality 0–1 against per-agent threshold |
| **Ground truth** | Human (interactive) | Monthly | 5 labelled samples, human rates 1–5, trends over time |

### Running evals

```bash
# CI — all structural checks (21 tests for keyword_research, stubs skip)
python -m pytest tests/evals/ -k "Structural"

# Or via eval_runner (also logs results to evals_log DB table)
python tests/evals/eval_runner.py structural [--agents keyword_research,gap_analyzer]

# Weekly relevance (requires LLM API key; runs agent live then judges output)
python tests/evals/eval_runner.py relevance [--agents keyword_research]

# Monthly ground truth (interactive, prompts for 1-5 score per sample)
python tests/evals/eval_runner.py ground-truth --agent keyword_research

# Trend report (queries evals_log, markdown table with improving/degrading/stable)
python tests/evals/eval_runner.py report [--days 30]
```

### Adding evals for a new agent

1. Create `tests/evals/<dept>/eval_<agent>.py` from any existing stub as template.
2. Set `IS_BUILT = True`.
3. Remove `@pytest.mark.skip` from `TestStructural_<agent>`.
4. Implement test bodies (check result fields, DB inserts, enum values).
5. Set `RELEVANCE_THRESHOLD` and fill `RELEVANCE_SAMPLE_INPUTS` / `RELEVANCE_JUDGE_CRITERIA`.
6. Fill `GROUND_TRUTH_SAMPLES` with 5 representative inputs + expected field checklist.

### DB table

`evals_log` stores all eval results (no RLS — operational data, not tenant data).
Indexes on `agent_name`, `run_at`, and `(agent_name, eval_type)` for trend queries.

---

## Development Workflow

- **Branch strategy**: `main` (prod) ← `staging` ← feature branches
- **PR requirements**: tests pass, type-check clean, one approval
- **Agent development**: `python scripts/run_agent.py --agent keyword_research --seed "ai marketing" --org test-org` to run any agent standalone
- **Local dev**: `docker compose up` starts PostgreSQL, Redis, API, worker, web
- **Testing agents**: each agent has unit tests with mocked LLM responses + integration tests against golden traces

---

## Coding Conventions

### Python (backend)
- Python 3.12+, async/await everywhere
- Pydantic v2 for all data contracts (input, output, config)
- SQLAlchemy 2.0 async ORM, Alembic for migrations
- Type hints on every function signature
- `ruff` for linting + formatting
- Tests: `pytest` + `pytest-asyncio`
- One file per agent, one file per integration
- All secrets from env vars via pydantic-settings, never hardcoded

### TypeScript (frontend)
- Next.js 14 App Router, React Server Components by default
- `"use client"` only when needed (interactivity, hooks)
- shadcn/ui for all UI primitives
- TanStack Query for server state
- Zod for form/API validation
- `biome` for lint + format
- API calls go through typed client generated from OpenAPI spec

### Database
- All tables have: `id` (uuid, default gen_random_uuid()), `org_id` (uuid, FK, RLS), `created_at`, `updated_at`
- RLS policy on every table: `USING (org_id = current_setting('app.current_org_id')::uuid)`
- Indexes: `org_id` on every table, `embedding` with ivfflat/hnsw on knowledge_chunks
- Migrations are additive-only in production (no destructive changes without a plan)

---

## Team Split (3-Person)

| Person | Owns | First Tasks |
|---|---|---|
| **Backend / Agent eng** | BaseAgent framework, all 45 agents, LLM router, preferences | Week 1: BaseAgent + LLMRouter + first 3 SEO agents |
| **Full-stack eng** | FastAPI routes, Next.js dashboard, auth, review UI | Week 1: project scaffold, auth, Docker Compose, DB schema |
| **Integrations / Infra** | All 13 integration modules, RAG pipeline, Terraform, CI/CD | Week 1: PostgreSQL+pgvector setup, GSC integration, base integration class |

All three collaborate on the DB schema in week 1. After that, work is parallelized.

---

## What To Build First (Weeks 1-3)

These are shared foundations. Nothing else works without them:

1. `docker-compose.yml` — PostgreSQL 16 + pgvector, Redis, API, worker
2. DB schema + Alembic — core tables above, RLS policies
3. `core/agent_base.py` — BaseAgent with preflight, execute, audit, notify
4. `core/llm_router.py` — tier config, provider fallback, cost tracking
5. `core/task_queue.py` — Celery/ARQ setup, async dispatch
6. `db/session.py` — async session factory with `SET app.current_org_id`
7. `integrations/base.py` — retry, rate-limit, circuit breaker
8. Auth + org onboarding flow
9. First working agent end-to-end: keyword_research (proves the framework)
10. `scripts/run_agent.py` — CLI for running any agent standalone

**Success criteria for week 3**: Run `python scripts/run_agent.py --agent keyword_research --seed "ai marketing"` and see: keywords written to DB, agent_run logged with cost, audit trail complete.

---

## Agent Build Checklist

**Every agent must pass ALL of these before moving to the next one.
No exceptions. No partial completions.**

### Phase 1 — Before writing any code

- [ ] Output contract defined in `apps/api/core/contracts.py`
      - Every field the agent writes to DB is in the Pydantic model
      - All field names match DB column names exactly
- [ ] DB model updated to match contract (no extra, no missing columns)
- [ ] Alembic migration generated and applied cleanly
      `uv run alembic upgrade head` — zero errors
- [ ] RLS policy covers any new table introduced
- [ ] Prompt written with UPPERCASE_PLACEHOLDER convention
      - No {curly_brace} placeholders
      - Includes concrete filled JSON example
      - States "Return ONLY JSON array, no markdown, no explanation"
- [ ] Prompt seeded in DB via seed_prompts.py
      `python scripts/seed_prompts.py`
      Verify: `SELECT agent_name, version, active FROM prompts;`

### Phase 2 — While writing the agent

- [ ] Agent class decorated with @register
- [ ] `name` and `tier` class attributes set correctly
- [ ] Prompt loaded from registry — never hardcoded
      `await PromptRegistry().get(self.name, ctx.db)`
- [ ] Placeholder replaced with `.replace()` — never f-string
      `prompt = template.replace("SEED_KEYWORD", value)`
- [ ] Raw LLM response printed before parsing (remove before production)
- [ ] JSON parser is defensive:
      - Strips markdown code blocks before parsing
      - Handles both string arrays and object arrays
      - Uses .get() with fallback key names for every field
      - Never counts raw items — counts successfully inserted rows
- [ ] DB write uses RLS-scoped session from ctx.db
- [ ] Verify row count inside session after INSERT:
      `count = await db.scalar(text("SELECT COUNT(*) FROM table"))`
- [ ] AgentResult returned with correct status, data, tokens_used

### Phase 3 — After writing the agent

- [ ] Unit test written with mocked LLM response
      `uv run pytest tests/unit/agents/<dept>/test_<agent>.py -v`
      All tests pass
- [ ] Agent runs via CLI without errors:
      `python scripts/run_agent.py --agent <name> --params '{}' --org <test-org-id>`
- [ ] DB rows verified — real data written, no empty fields:
```sql
      SET app.current_org_id = '00000000-0000-0000-0000-000000000001';
      SELECT * FROM <table> ORDER BY created_at DESC LIMIT 10;
```
- [ ] agent_runs row verified — status=success, tokens > 0, duration > 0:
```sql
      SELECT agent_name, status, tokens_in, tokens_out, duration_ms
      FROM agent_runs ORDER BY started_at DESC LIMIT 3;
```
- [ ] RLS verified — running same query under different org returns 0 rows:
```sql
      SET app.current_org_id = '99999999-9999-9999-9999-999999999999';
      SELECT COUNT(*) FROM <table>;  -- must return 0
```
- [ ] Golden trace saved in tests/golden_traces/<agent_name>_trace.json:
      {input_params, expected_output_fields, expected_db_table, min_rows}
- [ ] Prompt committed to seed_prompts.py (DB is not source of truth — script is)
- [ ] ISSUES_AND_FIXES.md updated if any new issue was encountered
- [ ] Agent status updated in CLAUDE.md agents build status table

### Phase 4 — Known failure modes to check per agent

- [ ] What happens if LLM returns empty response? → agent handles gracefully
- [ ] What happens if LLM returns plain strings instead of objects? → parser handles
- [ ] What happens if a required field is missing from LLM response? → .get() with default
- [ ] What happens if DB insert fails mid-batch? → partial results logged, not silently dropped
- [ ] What happens if prompt is missing from registry? → PromptNotFoundError raised immediately, not swallowed
- [ ] What happens if org has no brand_voice row? → agent uses empty defaults, does not crash

### Hard stops — these block everything

If any of these fail, stop. Fix before proceeding.

- Alembic migration fails → do not write agent code
- Unit tests fail → do not run via CLI
- CLI run produces 0 DB rows → do not mark agent as done
- RLS check returns rows from wrong org → critical, fix immediately
- agent_runs shows status=failed → read error column, fix root cause

---

## Agents Build Status

34 agents registered as of 2026-05-05. Remaining not-built: image_creator, video_producer, thumbnail_generator (video production pipeline).

---

## Frontend Pages Build Status

All 8 dashboard pages built as of 2026-05-05. Every page connects to real API endpoints — no mock data in components.

| Page | Route | Status | API endpoints used |
|---|---|---|---|
| Dashboard | `/dashboard` | ✅ | `/api/v1/keywords/stats`, `/api/v1/agents/runs`, `/api/v1/opportunities`, `/api/v1/articles`, `/api/v1/agents/{name}/run` |
| Keywords | `/keywords` | ✅ | `/api/v1/keywords`, `/api/v1/keywords/stats`, `/api/v1/keywords/research`, `/api/v1/keywords/validate` |
| Opportunities | `/opportunities` | ✅ | `/api/v1/opportunities`, `/api/v1/agents/content_director/run` |
| Content | `/content` | ✅ | `/api/v1/articles`, `PUT /api/v1/articles/{id}` |
| Competitors | `/competitors` | ✅ | `/api/v1/competitors`, `/api/v1/competitor-content` |
| Video Queue | `/video-queue` | ✅ | `/api/v1/video-jobs` (via dashboard router) |
| Strategy | `/strategy` | ✅ | `/api/v1/strategy-reports`, `/api/v1/agents/strategy_synthesizer/run` |
| Settings | `/settings` | ✅ | `/api/v1/brand-voice`, `/api/v1/settings/auto-mode` |

**Shared frontend files:**
- `apps/web/src/lib/types.ts` — all domain types (Opportunity, Article, Competitor, VideoJob, StrategyReport, BrandVoice, AutoModeSettings, etc.)
- `apps/web/src/lib/api.ts` — namespaced `api.*` client (keywords, runs, agents, opportunities, articles, competitors, strategy, brandVoice, autoMode, videoJobs)
- `apps/web/src/components/ui/badge.tsx` — Badge + `statusBadgeVariant()` helper

**Backend additions (supporting the dashboard):**
- `apps/api/api/v1/dashboard.py` — all 12 missing endpoint groups (opportunities, articles, social content, competitors, competitor-content, strategy-reports, rank-tracking, aeo-results, brand-voice, settings/auto-mode, video-jobs)
- `apps/api/api/v1/agents.py` — `GET /agents/runs` now accepts `?limit=` query param
- `apps/api/api/v1/router.py` — `dashboard.router` included

| Agent | Contract | Migration | Prompt | Unit Test | CLI Verified | DB Verified | RLS Verified | Golden Trace |
|---|---|---|---|---|---|---|---|---|
| keyword_research | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| keyword_validator | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| opportunity_scorer | ✅ | ✅ | n/a | ✅ | ✅ | ✅ | ✅ | ✅ |
| trend_collector | ✅ | ✅ | n/a | ✅ | ✅ | ✅ | ✅ | ✅ |
| competitor_monitor | ✅ | ✅ | n/a | ✅ | ✅ | ✅ | ✅ | ✅ |
| content_extractor | ✅ | ✅ | n/a | ✅ | ✅ | ✅ | ✅ | ✅ |
| keyword_overlap_analyzer | ✅ | n/a | n/a | ✅ | ✅ | ✅ | ✅ | ⬜ |
| site_auditor | ✅ | ✅ | n/a | ✅ | ✅ | ✅ | ✅ | ⬜ |
| gap_analyzer | ✅ | n/a | n/a | ✅ | ✅ | ✅ | ✅ | ✅ |
| rank_tracker | ✅ | ✅ | n/a | ✅ | ✅ | ✅ | ✅ | ✅ |
| aeo_scanner | ✅ | ✅ | n/a | ✅ | ✅ | ✅ | ✅ | ⬜ |
| threat_assessor | ✅ | n/a | n/a | ✅ | ✅ | ✅ | ✅ | ⬜ |
| preference_learner | ✅ | ✅ | n/a | ✅ | ✅ | ✅ | ✅ | ⬜ |
| document_ingester | ✅ | ✅ | n/a | ✅ | ⬜ | ⬜ | ⬜ | ⬜ |
| brand_voice_keeper | ✅ | n/a | n/a | ✅ | ✅ | ✅ | ✅ | ⬜ |
| rag_searcher | ✅ | n/a | n/a | ✅ | ✅ | ✅ | ✅ | ⬜ |
| internal_link_finder | ✅ | n/a | n/a | ✅ | ✅ | ✅ | ✅ | ⬜ |
| topic_discovery | ✅ | ✅ | n/a | ✅ | ✅ | ✅ | ✅ | ⬜ |
| article_planner | ✅ | ✅ | ✅ | ✅ | ⬜ | ⬜ | ⬜ | ⬜ |
| article_writer | ✅ | ✅ | ✅ | ✅ | ⬜ | ⬜ | ⬜ | ⬜ |
| content_director | ✅ | n/a | n/a | ✅ | ⬜ | ⬜ | n/a | ⬜ |
| linkedin_agent | ✅ | ✅ | ✅ | ✅ | ⬜ | ⬜ | ⬜ | ⬜ |
| twitter_agent | ✅ | ✅ | ✅ | ✅ | ⬜ | ⬜ | ⬜ | ⬜ |
| newsletter_agent | ✅ | ✅ | ✅ | ✅ | ⬜ | ⬜ | ⬜ | ⬜ |
| video_scriptwriter | ✅ | ✅ | ✅ | ✅ | ⬜ | ⬜ | ⬜ | ⬜ |
| lead_magnet_agent | ✅ | ✅ | ✅ | ✅ | ⬜ | ⬜ | ⬜ | ⬜ |
| competitor_discovery | ✅ | n/a | ✅ | ✅ | ⬜ | ⬜ | ⬜ | ⬜ |
| strategy_synthesizer | ✅ | ✅ | ✅ | ✅ | ⬜ | ⬜ | ⬜ | ⬜ |
| wordpress_publisher | ✅ | n/a | n/a | ✅ | ⬜ | ⬜ | n/a | ⬜ |
| ai_assistant | ✅ | n/a | ✅ | ✅ | ⬜ | ⬜ | n/a | ⬜ |
| pipeline_orchestrator | ✅ | n/a | n/a | ✅ | ⬜ | ⬜ | n/a | ⬜ |
| auto_mode_engine | ✅ | n/a | n/a | ✅ | ⬜ | ⬜ | n/a | ⬜ |
| video_handoff | ✅ | ✅ | n/a | ✅ | ⬜ | ⬜ | n/a | ⬜ |
| broll_selector | ✅ | ✅ | n/a | ✅ | ⬜ | ⬜ | ⬜ | ⬜ |

---

## Environment Variables

```bash
# Database
# DATABASE_URL     → vikas_app (restricted user, RLS enforced) — used by API runtime + agents
# ADMIN_DATABASE_URL → vikas (admin user, DDL privileges) — used by Alembic migrations ONLY
DATABASE_URL=postgresql+asyncpg://vikas_app:vikas_app_dev@localhost:5432/vikas
ADMIN_DATABASE_URL=postgresql+asyncpg://vikas:vikas_dev@localhost:5432/vikas
REDIS_URL=redis://localhost:6379/0

# LLM Providers
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_AI_API_KEY=...

# Integrations (per-org, stored encrypted in DB — these are defaults for dev)
GSC_SERVICE_ACCOUNT_JSON=...
GA4_PROPERTY_ID=...
WORDPRESS_URL=...
WORDPRESS_APP_PASSWORD=...

# Auth
SUPABASE_URL=...
SUPABASE_ANON_KEY=...

# Storage
S3_BUCKET=vikas-media
AWS_REGION=us-east-1

# App
ENV=development
LOG_LEVEL=DEBUG
DAILY_COST_LIMIT_USD=50.0
```
