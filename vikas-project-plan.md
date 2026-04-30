# Vikas — AI Marketing Platform: Project Plan

---

## 1. Project Structure

```
vikas/
├── apps/
│   ├── web/                          # Next.js 14 dashboard (App Router, RSC)
│   │   ├── app/
│   │   │   ├── (auth)/               # Login, signup, org onboarding
│   │   │   ├── (dashboard)/          # Main UI shell
│   │   │   │   ├── keywords/         # Keyword research & clusters
│   │   │   │   ├── content/          # Content pipeline, drafts, review queue
│   │   │   │   ├── competitors/      # Competitor intel dashboard
│   │   │   │   ├── video/            # Video production queue
│   │   │   │   ├── analytics/        # GSC/GA4 synthesis views
│   │   │   │   ├── knowledge/        # RAG KB, document uploads
│   │   │   │   ├── auto-mode/        # Nightly pipeline config + logs
│   │   │   │   ├── settings/         # Integrations, API keys, brand voice
│   │   │   │   └── chat/             # AI assistant interface
│   │   │   └── api/                  # Next.js API routes (BFF layer)
│   │   └── components/
│   │       ├── ui/                   # shadcn/ui primitives
│   │       └── domain/              # Content cards, scoring widgets, pipeline viz
│   │
│   └── api/                          # Python FastAPI backend
│       ├── main.py
│       ├── config/
│       │   ├── settings.py           # Env-based config (pydantic-settings)
│       │   └── model_tiers.py        # LLM routing config (fast/standard/advanced)
│       ├── core/
│       │   ├── agent_base.py         # BaseAgent class (preflight, cost tracking, audit)
│       │   ├── agent_registry.py     # Agent discovery & instantiation
│       │   ├── llm_router.py         # Multi-provider model selector
│       │   ├── cost_tracker.py       # Token usage & cost aggregation
│       │   ├── task_queue.py         # Async task dispatch (Celery/ARQ)
│       │   └── notifications.py      # Slack/email/webhook alerts
│       ├── db/
│       │   ├── models/               # SQLAlchemy models
│       │   │   ├── organizations.py  # Org + RLS policies
│       │   │   ├── keywords.py
│       │   │   ├── content.py
│       │   │   ├── competitors.py
│       │   │   ├── opportunities.py
│       │   │   ├── agent_runs.py     # Audit log: duration, cost, status
│       │   │   ├── preferences.py    # Human feedback + learned prefs
│       │   │   └── knowledge.py      # Document chunks + embeddings
│       │   ├── migrations/           # Alembic
│       │   └── session.py            # Async session factory + RLS context
│       ├── agents/
│       │   ├── seo/                  # Pillar 1 — 8 agents
│       │   │   ├── keyword_research.py
│       │   │   ├── keyword_validator.py
│       │   │   ├── topic_discovery.py
│       │   │   ├── gap_analyzer.py
│       │   │   ├── trend_collector.py
│       │   │   ├── aeo_scanner.py
│       │   │   ├── rank_tracker.py
│       │   │   └── site_auditor.py
│       │   ├── content/              # Pillar 2 — 9 agents
│       │   │   ├── content_director.py    # Orchestrator
│       │   │   ├── article_planner.py
│       │   │   ├── article_writer.py
│       │   │   ├── newsletter_agent.py
│       │   │   ├── linkedin_agent.py
│       │   │   ├── twitter_agent.py
│       │   │   ├── video_scriptwriter.py
│       │   │   ├── lead_magnet_agent.py
│       │   │   └── image_creator.py
│       │   ├── competitor/           # Pillar 3 — 5 agents
│       │   │   ├── competitor_monitor.py
│       │   │   ├── content_extractor.py
│       │   │   ├── keyword_overlap.py
│       │   │   ├── threat_assessor.py
│       │   │   └── competitor_discovery.py
│       │   ├── video/                # Pillar 4 — 4 agents
│       │   │   ├── script_generator.py
│       │   │   ├── broll_selector.py
│       │   │   ├── video_producer.py
│       │   │   └── thumbnail_generator.py
│       │   ├── knowledge/            # Pillar 5 — 7 agents
│       │   │   ├── document_ingester.py
│       │   │   ├── brand_voice_keeper.py
│       │   │   ├── rag_searcher.py
│       │   │   ├── internal_link_finder.py
│       │   │   ├── wordpress_publisher.py
│       │   │   ├── pipeline_orchestrator.py
│       │   │   └── ai_assistant.py
│       │   └── orchestration/        # Auto Mode — 4 agents
│       │       ├── auto_mode_engine.py
│       │       ├── content_director_orchestrator.py
│       │       ├── opportunity_scorer.py
│       │       └── strategy_synthesizer.py
│       ├── integrations/             # 13+ shared modules
│       │   ├── base.py               # BaseIntegration (auth, retry, rate-limit)
│       │   ├── google_search_console.py
│       │   ├── google_analytics.py
│       │   ├── seo_data_provider.py   # Ahrefs/DataForSEO/etc
│       │   ├── wordpress.py
│       │   ├── hubspot.py
│       │   ├── linkedin_api.py
│       │   ├── twitter_api.py
│       │   ├── google_trends.py
│       │   ├── web_crawler.py         # Playwright/httpx-based
│       │   ├── ai_avatar.py           # HeyGen/Synthesia
│       │   ├── image_gen.py           # DALL-E/Midjourney/Flux
│       │   └── social_listener.py
│       ├── rag/
│       │   ├── embeddings.py          # Embedding generation (pgvector)
│       │   ├── chunker.py             # Document splitting strategies
│       │   ├── retriever.py           # Similarity search + reranking
│       │   └── brand_voice.py         # Style vector matching
│       ├── preferences/
│       │   ├── feedback_store.py      # Approve/edit/reject tracking
│       │   ├── preference_learner.py  # Pattern extraction from feedback
│       │   └── injection.py           # Inject preferences into agent prompts
│       ├── api/
│       │   ├── v1/
│       │   │   ├── agents.py          # Trigger/status/history endpoints
│       │   │   ├── keywords.py
│       │   │   ├── content.py
│       │   │   ├── competitors.py
│       │   │   ├── knowledge.py
│       │   │   ├── analytics.py
│       │   │   ├── auto_mode.py
│       │   │   └── chat.py            # Streaming AI assistant
│       │   └── deps.py                # Auth, org context, DB session
│       └── workers/
│           ├── scheduler.py           # APScheduler / cron config
│           ├── nightly_pipeline.py    # Auto Mode 2AM UTC trigger
│           └── event_handlers.py      # Webhook + pub/sub consumers
│
├── packages/
│   ├── shared-types/                  # TypeScript types shared between apps
│   └── agent-sdk/                     # Python: agent protocol + testing utils
│
├── infra/
│   ├── docker/
│   │   ├── Dockerfile.api
│   │   ├── Dockerfile.web
│   │   ├── Dockerfile.worker
│   │   └── docker-compose.yml        # Local dev stack
│   ├── terraform/                     # AWS/GCP IaC
│   │   ├── modules/
│   │   │   ├── vpc/
│   │   │   ├── rds/                   # PostgreSQL + pgvector
│   │   │   ├── ecs/                   # API + worker services
│   │   │   ├── redis/                 # Task queue broker + caching
│   │   │   ├── s3/                    # Media storage
│   │   │   ├── cloudfront/
│   │   │   └── monitoring/            # CloudWatch + Grafana
│   │   ├── environments/
│   │   │   ├── staging/
│   │   │   └── production/
│   │   └── main.tf
│   └── k8s/                           # Optional: Kubernetes manifests
│       ├── api/
│       ├── worker/
│       └── web/
│
├── tests/
│   ├── unit/
│   │   ├── agents/                    # Per-agent unit tests
│   │   ├── integrations/
│   │   └── rag/
│   ├── integration/
│   │   ├── pipelines/                 # End-to-end pipeline tests
│   │   └── api/
│   └── golden_traces/                 # Regression: expected agent trajectories
│
├── scripts/
│   ├── seed_db.py                     # Initial data + demo org
│   ├── run_agent.py                   # CLI: run any agent standalone
│   └── benchmark_models.py            # Cost/quality comparison across providers
│
├── .github/
│   └── workflows/
│       ├── ci.yml                     # Lint, test, type-check
│       ├── deploy-staging.yml
│       └── deploy-prod.yml
│
├── turbo.json                         # Turborepo config
├── pyproject.toml                     # Python workspace (uv/poetry)
└── README.md
```

---

## 2. Infrastructure Architecture

```
                        ┌─────────────────┐
                        │   CloudFront     │
                        │   (CDN + WAF)    │
                        └────────┬────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                   │
     ┌────────▼────────┐  ┌─────▼──────┐   ┌───────▼───────┐
     │  Next.js (web)  │  │  FastAPI    │   │  Worker Pool  │
     │  Vercel / ECS   │  │  ECS/GKE   │   │  ECS/GKE      │
     │  SSR + RSC      │  │  Auto-scale │   │  Celery + ARQ │
     └────────┬────────┘  └─────┬──────┘   └───────┬───────┘
              │                 │                   │
              └────────┬────────┴───────────────────┘
                       │
          ┌────────────┼────────────┐
          │            │            │
  ┌───────▼──────┐ ┌───▼───┐ ┌─────▼─────┐
  │ PostgreSQL   │ │ Redis │ │    S3      │
  │ + pgvector   │ │       │ │  (media)   │
  │ RDS (RLS)    │ │ Cache │ │            │
  └──────────────┘ │ Queue │ └───────────┘
                   └───────┘
```

**Key infrastructure decisions:**

- **Database**: PostgreSQL 16 + pgvector extension. Single DB for relational + vector search. RLS policies enforce org-level tenant isolation. No separate vector DB needed.
- **Task queue**: Redis-backed (Celery or ARQ). Workers auto-scale by queue depth. Separate queues per priority: `critical` (publishing), `standard` (content gen), `batch` (nightly scans).
- **LLM routing**: LiteLLM or custom router. Supports OpenAI, Anthropic, Google, open-source via OpenRouter. Automatic fallback on provider failures.
- **Secrets**: AWS Secrets Manager / GCP Secret Manager. Per-org API keys encrypted at rest.
- **Observability**: OpenTelemetry → Grafana stack. Every agent run gets a trace with: model used, tokens in/out, cost, latency, pass/fail.
- **CI/CD**: GitHub Actions → staging (auto-deploy on merge) → production (manual promotion).

---

## 3. Core Framework Design

### BaseAgent Contract

```python
class BaseAgent(ABC):
    def preflight(self, ctx: AgentContext) -> PreflightResult:
        """Validate config, check quotas, verify integrations."""

    @abstractmethod
    async def execute(self, ctx: AgentContext) -> AgentResult:
        """Core logic. Subclasses implement this."""

    async def run(self, ctx: AgentContext) -> AgentResult:
        """Preflight → execute → audit log → notify → return."""
```

Every agent gets: cost tracking, retry logic (exponential backoff), circuit breaker on integration failures, structured JSON logging, and org-scoped DB access via RLS.

### LLM Router Logic

```
Task → model_tiers.yaml lookup → provider availability check → cost gate → route
  │
  ├── Fast tier   → GPT-4o-mini / Claude Haiku / Gemini Flash
  ├── Standard    → GPT-4o / Claude Sonnet / Gemini Pro
  └── Advanced    → Claude Opus / GPT-4o (high-temp) / o1
```

Fallback chain: primary provider → secondary → tertiary. If all fail, task goes to dead-letter queue with alert.

---

## 4. Data Model (Core Entities)

| Entity | Purpose | Key Relations |
|---|---|---|
| `organizations` | Tenant root, RLS anchor | owns everything below |
| `keywords` | Seed → validated → clustered | → opportunities, content |
| `keyword_clusters` | Grouped keywords by intent | → content plans |
| `opportunities` | Scored content opportunities | ← keywords, trends, competitors |
| `content_items` | Drafts, published pieces | ← opportunities, → reviews |
| `content_reviews` | 9-dimension scoring results | ← content_items |
| `competitors` | Tracked competitor domains | → competitor_content |
| `competitor_content` | Extracted competitor articles | → threat_scores |
| `trend_signals` | Raw trend data from 11 sources | → opportunities |
| `agent_runs` | Audit log per execution | agent, duration, cost, status, error |
| `preferences` | Learned from human feedback | injected into prompts |
| `knowledge_chunks` | RAG: text chunks + embeddings | pgvector cosine similarity |
| `brand_voice` | Tone, banned words, style rules | pulled by every content agent |
| `pipeline_runs` | Auto Mode nightly run tracking | → agent_runs (children) |

---

## 5. Implementation Timeline (16 Weeks)

### Phase 1: Foundation (Weeks 1–3)
- Project scaffolding (monorepo, CI/CD, Docker dev env)
- PostgreSQL schema + pgvector + RLS policies + Alembic migrations
- `BaseAgent` framework: preflight, execute, audit, cost tracking
- `LLMRouter` with 3 tiers, 3 providers, fallback chains
- Redis task queue setup (Celery/ARQ)
- Auth layer (Supabase Auth or Clerk) + org onboarding flow
- **Deliverable**: Any developer can create a new agent in <30 min

### Phase 2: SEO Pipeline — Pillar 1 (Weeks 4–6)
- 8 SEO agents: keyword research → validator → gap → rank tracker → site auditor → trend → AEO → topic discovery
- Integration modules: GSC, GA4, SEO data provider
- Dashboard pages: keyword explorer, cluster view, rank tracking
- **Deliverable**: Seed keyword → validated cluster → scored opportunities, end-to-end

### Phase 3: Content Production — Pillar 2 (Weeks 6–9)
- 9 content agents: director → planner → writer → social × 2 → newsletter → video script → lead magnet → image
- RAG pipeline: document ingester → chunker → embeddings → retriever
- Brand voice system: guidelines store + past content RAG + preference injection
- Content review UI: 9-dimension scoring, approve/edit/reject flow
- Preference learner: extract patterns from feedback, inject into future prompts
- **Deliverable**: Opportunity → multi-format content → review queue, with brand voice

### Phase 4: Competitor Intel + Video — Pillars 3 & 4 (Weeks 9–11)
- 5 competitor agents: monitor → extractor → overlap → threat → discovery
- Web crawler integration (Playwright headless)
- 4 video agents: script → b-roll → producer → thumbnail
- AI avatar integration (HeyGen/Synthesia)
- Dashboard: competitor threat board, video production queue
- **Deliverable**: Automated daily competitor scans, content-to-video pipeline

### Phase 5: Auto Mode + Orchestration (Weeks 11–13)
- Auto Mode engine: nightly scheduler (2AM UTC cron)
- Pipeline: scan → score → select (daily caps) → inject prefs → draft → queue → notify
- Opportunity scorer: search potential × competitive gap × trend momentum × engagement
- Content Director orchestrator: format selection, parallel dispatch
- Strategy synthesizer: weekly rollup report
- Human-in-the-loop: approve/edit/reject with feedback loop closure
- **Deliverable**: Fully autonomous nightly pipeline with morning review queue

### Phase 6: Publishing + Knowledge Ops — Pillar 5 (Weeks 13–15)
- WordPress publisher (REST API: HTML, Yoast meta, images, categories)
- HubSpot publisher
- Social platform publishing (LinkedIn, X)
- Internal link finder agent
- AI chat assistant (streaming, agent triggering, KB search)
- Knowledge base management UI
- **Deliverable**: One-click publish across all channels, chat-based system access

### Phase 7: Hardening + Launch (Weeks 15–16)
- Load testing (Locust): 50 concurrent agent runs, 10 concurrent users
- Security audit: RLS validation, API key encryption, OWASP top 10
- Observability: Grafana dashboards (agent cost/run, pipeline success rate, model latency)
- Golden trace regression tests for all critical pipelines
- Documentation: API docs (OpenAPI), agent catalog, runbooks
- Staging → production promotion
- **Deliverable**: Production-ready platform

---

## 6. Key Risk Mitigations

| Risk | Mitigation |
|---|---|
| LLM provider outages | Multi-provider fallback chain + circuit breakers |
| Runaway agent costs | Per-org daily token budget caps, kill switch on budget breach |
| Prompt drift over time | Golden trace regression tests, weekly prompt review cadence |
| Data leakage between tenants | PostgreSQL RLS enforced at session level, tested in CI |
| Integration API changes | Adapter pattern per integration, version-pinned clients |
| Content quality regression | 9-dimension review scoring gate, nothing auto-publishes without approval |

---

## 7. Team Composition (Recommended)

| Role | Count | Focus |
|---|---|---|
| Backend / AI engineer | 2–3 | Agent framework, LLM routing, integrations |
| Frontend engineer | 1–2 | Dashboard, review UI, chat interface |
| Data / ML engineer | 1 | RAG pipeline, embeddings, preference learning |
| DevOps / Platform | 1 | Infra, CI/CD, observability, security |
| Product / QA | 1 | Agent testing, golden traces, acceptance criteria |

**Total**: 6–8 engineers for 16-week delivery.

---

## 8. Tech Stack Summary

| Layer | Choice | Rationale |
|---|---|---|
| Frontend | Next.js 14, TypeScript, shadcn/ui, TanStack Query | RSC for fast loads, type-safe, real-time updates |
| API | FastAPI, Python 3.12, Pydantic v2 | Async-native, schema validation, OpenAPI auto-gen |
| Agents | Custom Python framework | Full control over routing, cost, audit — no framework lock-in |
| LLM routing | LiteLLM or custom | 100+ models, automatic fallback, cost tracking |
| Database | PostgreSQL 16 + pgvector | Relational + vector in one DB, RLS for multi-tenancy |
| Queue | Redis + Celery/ARQ | Proven, simple, per-priority queues |
| Storage | S3 / GCS | Media, generated images, video assets |
| Infra | Terraform, ECS or GKE, GitHub Actions | Reproducible, auto-scaling, standard CI/CD |
| Monitoring | OpenTelemetry → Grafana + Loki + Tempo | Traces per agent run, cost dashboards, alerting |
