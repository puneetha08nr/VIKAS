# ISSUES_AND_FIXES.md

Running log of bugs, surprises, and their fixes. Update this file whenever you hit a new issue.
Add the agent/component name, symptom, root cause, and exact fix. This file is the institutional memory that prevents re-debugging the same problems.

---

## Bug Log

### BUG-UI-021 — composite_score exceeds 10.0 for commercial-intent keywords

**Severity:** Low  
**Component:** `apps/api/agents/seo/opportunity_scorer.py`, `apps/web/src/app/(dashboard)/opportunities/page.tsx`

**Symptom:** "project management software" displayed `composite_score = 10.09` in the UI (bar overflowed to 100.9%, score label showed ">10"). The 0-10 score contract was violated.

**Root cause:** `compute_composite` applies an intent multiplier (1.5× for commercial, 1.3× for transactional) on top of a `weighted_sum` that itself can reach 10.0. Max raw composite = 10.0 × 1.5 = 15.0. No cap existed.

**Fix:**
- Backend: `composite = round(min(weighted_sum * intent_multiplier, 10.0), 3)` in `compute_composite()`
- UI: `Math.min(value, 10).toFixed(2)` for the score label in `CompositeScoreBar`
- DB: one stale row at 10.087 backfilled to 10.0 via `UPDATE opportunities SET composite_score = 10.0 WHERE composite_score > 10.0`

**Test added:** `test_composite_score_capped_at_10` — a perfect commercial keyword (max volume, zero KD, high CPC) must produce `score_range.max <= 10.0`.

**Files changed:**
- `apps/api/agents/seo/opportunity_scorer.py` — `min(..., 10.0)` in compute_composite
- `apps/web/src/app/(dashboard)/opportunities/page.tsx` — `Math.min(value, 10)` in label
- `tests/unit/agents/seo/test_opportunity_scorer.py` — new cap test

---

### BUG-UI-019 — Ollama provider name exposed in validation progress banner

**Severity:** High (internal tooling exposed to users)  
**Component:** `apps/web/src/app/(dashboard)/keywords/page.tsx`

**Symptom:** When "Validate All" ran, the progress banner showed "Est. 4 min on Ollama." — exposing the LLM provider name to users and implying LLM is used for validation.

**Root cause — two issues:**
1. Banner had hardcoded `"Est. {Math.ceil(validatingCount * 6 / 60)} min on Ollama."` based on 6s/keyword Ollama latency assumption.
2. Deeper: `keyword_validator.py` was **actually calling `self.call_llm()`** (step 6 in `execute()`) despite the architecture decision that keyword_validator is a pure rules engine. The LLM call was doing batch validation scoring on top of hard rules — unnecessary and against the spec.

**Fix:**
- Removed the estimation banner text entirely (no reliable estimate for rules-based agent).
- Removed the `call_llm()` call from `keyword_validator.execute()`. The agent now validates purely via hard rules: archive if volume<50, kd>9, or navigational intent; validate everything else.
- Removed `PromptRegistry` and `LLMUnavailableError` imports from the agent.
- `tokens_used=0, cost_usd=0.0` are now returned correctly.
- Updated 6 unit tests that were asserting LLM behavior (renamed to reflect pure-rules intent).
- Legacy LLM helper functions (`_parse_validation_json`, `_batches`) retained in module to avoid breaking test imports; marked as legacy.

**Files changed:**
- `apps/api/agents/seo/keyword_validator.py` — removed LLM call, simplified execute()
- `tests/unit/agents/seo/test_keyword_validator.py` — updated 6 tests
- `apps/web/src/app/(dashboard)/keywords/page.tsx` — removed Ollama estimate text

---

### BUG-A-004 — GET /api/v1/opportunities returns 500 (asyncpg rejects `::uuid[]` cast on bind parameter)

**Severity:** High  
**Component:** `apps/api/api/v1/dashboard.py` — `list_opportunities()`

**Symptom:** `GET /api/v1/opportunities` always returned HTTP 500 even though 82 rows existed in the DB. The harness B3 check (API auth enforcement) failed because the endpoint crashed before auth logic could return 200.

**Root cause:** The keyword enrichment subquery used:
```sql
SELECT id::text, keyword FROM keywords WHERE id = ANY(:ids::uuid[])
```
asyncpg's parameter parser sees `:ids::uuid[]` and treats `::uuid[]` as part of the bind-parameter name, producing a `PostgresSyntaxError: syntax error at or near ":"`. This is a known asyncpg limitation — `::` PostgreSQL casts cannot be placed immediately after a SQLAlchemy-style `:param` bind placeholder.

**Fix:** Cast the column side, not the parameter side:
```sql
SELECT id::text, keyword FROM keywords WHERE id::text = ANY(:ids)
```
`ids` is already a `list[str]` (UUID strings), so comparing against a text array works identically with no cast needed on the bind parameter. asyncpg handles `list[str]` for `ANY(:ids)` without issue.

**Files changed:**
- `apps/api/api/v1/dashboard.py` line 68 — one-line SQL change

**Verified:** `curl http://localhost:8000/api/v1/opportunities -H "X-Dev-Auth: bypass"` → 200 with 50 opportunities. Harness B3 and B4 now green.

**Pattern to remember:** Never write `:param::type` in asyncpg SQL. Always cast the column (`col::text`) or use ORM `.in_()` instead.

---

### BUG-UI-020 — `llm_estimate` data_source exposed as raw string in keyword table

**Severity:** Medium  
**Component:** `apps/web/src/app/(dashboard)/keywords/components/KeywordsTable.tsx`

**Symptom:** 122 keywords in DB have `data_source='llm_estimate'` (written before DECISION-001 removed LLM metric estimation). The `DataSourceBadge` component had no case for `llm_estimate` — fell through to the raw-value fallback, showing "llm_estimate" as visible text in the Source column.

**Root cause:** `DataSourceBadge` only handled `'dataforseo'` and `'pending'`; `'llm_estimate'` was a pre-DECISION-001 value that survived in the DB.

**Fix:** Added `|| source === 'llm_estimate'` to the `'pending'` branch in `DataSourceBadge`. Both values now render as the amber "Metrics pending" badge with tooltip "Metrics unavailable. Use Fetch metrics to backfill from DataForSEO." Semantically correct — both states mean real metrics are not yet available.

**Files changed:**
- `apps/web/src/app/(dashboard)/keywords/components/KeywordsTable.tsx`

---

### BUG-UI-018 — No per-row indication when individual keyword is validating

**Severity:** Medium  
**Component:** `KeywordsTable.tsx` + `keywords/page.tsx`

**Symptom:** Clicking the row-level "Validate" button gave no feedback on which row was in progress. The global validation banner ("Validating N keywords…") appeared, but no visual change on the specific row being processed.

**Fix:**
- Added `validatingRowId: string | null` state to `page.tsx`.
- `handleValidateRow()` sets it immediately when the button is clicked (before the API call completes), clears it on run success/failure.
- Added `validatingId?: string | null` prop to `KeywordsTable`.
- When `kw.id === validatingId`: row background → `bg-amber-50`, status badge → amber spinner + "Validating…" text, Validate/Create content buttons hidden.
- State is independent of `validateRunId` so it only activates for single-row validation, not bulk validate-all.

**Files changed:**
- `apps/web/src/app/(dashboard)/keywords/components/KeywordsTable.tsx`
- `apps/web/src/app/(dashboard)/keywords/page.tsx`

---

### BUG-A-003 — keyword_validator: invalid input accepted and queued silently

**Severity:** High  
**Component:** keyword_validator / `POST /api/v1/keywords/validate`  
**Harness check:** B5

**Symptom:** Sending `{"keyword_ids": "not-a-list"}` to the validate endpoint returned 202 and silently enqueued a Celery task instead of rejecting with 422. The test harness yaml's `api_write_endpoint` was also pointing at `/validate-all` (which accepts no body), causing the B5 check to test the wrong endpoint entirely.

**Root cause — two issues:**
1. `ValidateBody.keyword_ids` had no Pydantic-level constraint; the empty-list guard was a manual `if not body.keyword_ids: raise HTTPException` *inside* the handler, which ran after the Celery queue was not yet called but after Pydantic had already accepted bad types.
2. `tests/agent_configs/keyword_validator.yaml` had `api_write_endpoint: "POST /api/v1/keywords/validate-all"` — that endpoint takes no body at all, so the B5 invalid body was ignored and a 202 was returned.

**Fix:**
- `ValidateBody.keyword_ids` now uses `Field(min_length=1)` — Pydantic rejects empty lists and wrong types before the handler body runs; FastAPI returns 422 automatically.
- Removed the now-redundant manual `HTTPException` guard inside `run_validate`.
- Updated yaml: `api_write_endpoint` → `"POST /api/v1/keywords/validate"` (the endpoint that actually parses a body with `keyword_ids`).
- Yaml: `uses_llm: false` (A7 false failure — keyword_validator is a pure rules engine; `tokens_in=0` is correct behaviour, not a bug).

**Files changed:**
- `apps/api/api/v1/keywords.py` — `Field(min_length=1)` on `ValidateBody`, removed manual guard
- `tests/agent_configs/keyword_validator.yaml` — `uses_llm: false`, `api_write_endpoint` fixed, `skip_concurrent: false`

---

## Architectural Decisions

### DECISION-001 — Removed LLM metric estimation for keywords

**Date:** 2026-05-06  
**Status:** ✅ Implemented

**Decision:** Removed `_llm_keyword_fallback()` from `keyword_research.py`. LLM-estimated SEO metrics (volume, KD, CPC) are no longer saved for any keywords.

**Reason:** LLM-estimated SEO metrics create false confidence. Volume, KD, and CPC are empirical measurements — an LLM cannot know actual Google search counts, advertiser bid prices, or competition density. Presenting LLM guesses as metrics misleads the user into making real editorial decisions on invented numbers. Industry standard is NULL metrics with a pending state until real API data is available.

**New behaviour:**
- DataForSEO succeeds → keywords saved with real metrics, `data_source='dataforseo'`
- DataForSEO fails → keywords saved from Google Suggest with `volume=NULL, kd=NULL, cpc=NULL, data_source='pending'`
- UI shows amber "Metrics pending" badge for pending keywords; volume/KD/CPC columns show "—"
- "Fetch metrics" button appears when pending keywords exist → calls `POST /api/v1/keywords/fetch-metrics` → backfills from DataForSEO once configured

**Files changed:**
- `apps/api/agents/seo/keyword_research.py` — removed `_llm_keyword_fallback()`, inline pending fallback, NULL-safe metric handling in `_save_keywords`
- `apps/api/core/contracts.py` — `_KeywordMetricsMixin.data_source` default changed `"llm_estimate"` → `"pending"`
- `apps/api/db/models/keywords.py` — `server_default` changed `"llm_estimate"` → `"pending"`
- `apps/api/api/v1/keywords.py` — added `POST /fetch-metrics` endpoint
- `apps/web/src/lib/api.ts` — added `api.keywords.fetchMetrics()`
- `apps/web/src/app/(dashboard)/keywords/components/KeywordsTable.tsx` — `DataSourceBadge` handles `"pending"` → amber badge
- `apps/web/src/app/(dashboard)/keywords/page.tsx` — "Fetch metrics (N)" button in header

---

## keyword_research agent

### BUG-A-001 — DataForSEO 403 not caught by fallback; agent returns failed instead of degrading

**Severity:** High  
**Status:** ✅ FIXED

**Symptom:** DataForSEO returns 403 Forbidden (zero account balance). Agent status = `failed` instead of falling back to LLM estimates with `data_source = llm_estimate`.

**Root cause (two parts):**
1. The agent's `except IntegrationError` block (lines 49-62) returned `status="failed"` immediately — there was no fallback path at all. The `data_source` field was also hardcoded as `'dataforseo'` in `_save_keywords`, making it impossible to tag keywords from other sources.
2. Note: the base integration layer was NOT the bug — `base.py` correctly converts 403 → `httpx.HTTPStatusError` → `IntegrationError`. The `IntegrationError` was being caught; it just wasn't being handled correctly.

**Fix:**
- `keyword_research.py`: replaced the `return AgentResult(status="failed")` with a call to `_llm_keyword_fallback()`. When DataForSEO raises any `IntegrationError`, the agent now: (a) fetches suggestions from Google Suggest (free, no auth), (b) calls the LLM to estimate volume/KD/CPC/intent, (c) saves with `data_source='llm_estimate'`, (d) returns `status='partial'`.
- Added double-resilience: if the LLM itself also fails (no keys, quota), bare Google Suggest keywords are saved with default metrics rather than crashing.
- `_save_keywords()`: added `data_source` parameter (default `'dataforseo'`) to allow LLM-estimated rows to be tagged correctly.
- `_test_agent_runner.py`: increased happy-path CLI timeout from 60s → 180s for `uses_llm: true` agents (LLM calls can take 60-160s on cold start with provider fallback).
- Updated unit tests: `test_dataforseo_error_results_in_failed_status` and `test_dataforseo_error_message_is_descriptive` replaced with `test_dataforseo_error_triggers_llm_fallback` and `test_dataforseo_403_triggers_llm_fallback` — both verify `status=partial` and `data_source=llm_estimate`.

**Verification:**
- A7: `status=partial, duration=159436ms, tokens_in=268, tokens_out=825, cost=$0.0000, error=None`
- DB: keywords written with `data_source='llm_estimate'`
- `./scripts/test_agent.sh keyword_research` → ✅ ALL CHECKS PASSED

---

### Issue 1 — LLM returned plain string array, keywords_found=9 but 0 DB rows
**Symptom:** `AgentResult` reported `keywords_found: 9`, `status: success`, but `SELECT COUNT(*) FROM keywords` returned 0.

**Root cause:** Ollama (llama3.2:3b) returned a JSON array of plain strings — `["ai tools", "marketing automation", ...]` — instead of an array of objects. `_parse_keyword_json` only appended `isinstance(item, dict)` items, silently dropping string items. `keywords_found` counted the parsed list *before* DB insertion, not successfully inserted rows.

**Fix:** Added string-item handling in `_parse_keyword_json`:
```python
elif isinstance(item, str) and item.strip():
    result.append({"keyword": item.strip()})
```
Also: `keywords_found` still reflects parsed count (acceptable), but the insert loop logs warnings on failures so drops are never silent.

---

### Issue 2 — `intent` and `reason` fields were parsed but not persisted
**Symptom:** Keywords inserted, but `intent` and `reason` columns were always NULL even when the LLM returned them.

**Root cause:** The original `_save_keywords` INSERT statement didn't include `intent` or `reason` in the column list or params dict.

**Fix:** Added both columns to the INSERT:
```sql
INSERT INTO keywords (id, org_id, keyword, volume, kd, cpc, intent, reason, status, source_agent, created_at, updated_at)
VALUES (gen_random_uuid(), :org_id, :keyword, :volume, :kd, :cpc, :intent, :reason, 'raw', :source_agent, now(), now())
```
With multi-key fallbacks in params:
```python
"intent": str(kw.get("intent") or kw.get("search_intent") or "").strip() or None,
"reason": str(kw.get("reason") or kw.get("rationale") or kw.get("why") or "").strip() or None,
```

---

### Issue 3 — Prompt template using f-string left `{seed}` as literal text
**Symptom:** LLM received the prompt with the literal string `{seed}` instead of the actual seed keyword. The LLM generated keywords about `{seed}` as a topic.

**Root cause:** Prompt building used `f"{prompt_template}\n\nSeed keyword: {seed}"`. If `prompt_template` itself contained Python f-string-style braces (e.g. `{target_audience}`), Python would try to interpolate them and raise `KeyError`, or silently leave them if they weren't in scope.

**Fix:** Switched to `.replace()` with an UPPERCASE placeholder:
```python
prompt = prompt_template.replace("SEED_KEYWORD", seed)
```
Prompt template uses `SEED_KEYWORD` (not `{seed}`). Convention: all prompt placeholders are `UPPERCASE_WORDS`, never `{curly_brace}` style.

---

### Issue 4 — Alembic "Target database is not up to date" on autogenerate
**Symptom:** `uv run alembic revision --autogenerate -m "..."` exited with `Target database is not up to date`.

**Root cause:** The DB had unapplied migrations. Alembic requires the DB to be at `head` before it can autogenerate a new revision.

**Fix:** Always run `uv run alembic upgrade head` before `alembic revision --autogenerate`. From `apps/api/`, not the repo root.

---

### Issue 5 — `DuplicateColumnError: column "intent" already exists` on migration upgrade
**Symptom:** Running the autogenerated migration failed with `DuplicateColumnError` for `intent`.

**Root cause:** The `intent` column had been added to the DB manually (outside Alembic tracking) during earlier development. Autogenerate saw it in the ORM model and generated a standard `add_column` which failed on the already-existing column.

**Fix:** Rewrote the migration to use PostgreSQL's `IF NOT EXISTS` guard via raw SQL:
```python
def upgrade() -> None:
    op.execute("ALTER TABLE keywords ADD COLUMN IF NOT EXISTS intent VARCHAR(50)")
    op.execute("ALTER TABLE keywords ADD COLUMN IF NOT EXISTS reason TEXT")
    op.execute("ALTER TABLE keywords ADD COLUMN IF NOT EXISTS source_run_id UUID")
```
Rule: whenever a column might already exist in the DB (e.g. added manually for testing), use `IF NOT EXISTS`.

---

## Docker / Dev environment

### Issue 6 — Port 3000 EADDRINUSE on Next.js dev server startup
**Symptom:** `docker compose up` failed to start the `web` service: `Error: listen EADDRINUSE: address already in use :::3000`.

**Root cause:** A previous `vikas-web-1` container was still running and holding port 3000.

**Fix:** `docker stop vikas-web-1` before restarting. More durable fix: always `docker compose down` instead of `docker compose stop` to fully remove containers before rebuilding.

---

### Issue 7 — EACCES permission denied on `.next` files after Docker rebuild
**Symptom:** Next.js dev server crashed with `EACCES: permission denied, open '.next/...'` after rebuilding the `web` service.

**Root cause:** A prior Docker run had written the `.next` build cache as `root` to the host-mounted volume (`../../apps/web`). After switching users or rebuilding, the Next.js process couldn't overwrite root-owned files.

**Fix:** Added a named Docker volume for `.next`:
```yaml
# docker-compose.yml
volumes:
  - ../../apps/web:/app/apps/web
  - web_next_cache:/app/apps/web/.next   # ← named volume, not host mount
```
Named volumes are owned by the container user, so the Next.js process can write freely. The `.next` cache is ephemeral anyway — no value in persisting it to the host.

---

## Database / Migrations

### Issue 9 — `vikas_app` role had no password; connection from host failed
**Symptom:** `python scripts/run_agent.py` raised `asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "vikas_app"` even though the role existed in PostgreSQL.

**Root cause:** The `vikas_app` role was created without a password (`ALTER ROLE vikas_app ...` without `PASSWORD`). Inside the container peer auth works, but asyncpg connecting from the host requires password auth.

**Fix:** Set the password to match `.env`:
```sql
ALTER ROLE vikas_app PASSWORD 'vikas_app_dev';
```
**Prevention:** Include `ALTER ROLE vikas_app PASSWORD '...'` in the DB init script / `seed_db.py` so new dev environments never hit this.

---

### Issue 10 — `ADMIN_DATABASE_URL` merged onto same line as `NEXT_PUBLIC_SUPABASE_ANON_KEY` in `.env`
**Symptom:** `pydantic_settings` raised `ValidationError: admin_database_url Field required` even though `ADMIN_DATABASE_URL` appeared to be set in `.env`.

**Root cause:** A missing newline in `.env` caused the line to read:
```
NEXT_PUBLIC_SUPABASE_ANON_KEY=sb_publishable_...ADMIN_DATABASE_URL=postgresql+asyncpg://...
```
`python-dotenv` parsed this as a single key (`NEXT_PUBLIC_SUPABASE_ANON_KEY`) with a value that happened to contain the string `ADMIN_DATABASE_URL=...`. The `ADMIN_DATABASE_URL` key was never set.

**Fix:** Split the line into two separate entries in `.env`.

**Detection:** Always `grep ADMIN_DATABASE_URL .env` and verify the output is exactly one line with no prefix content.

---

## Eval framework

### Issue 11 — `_make_ctx` always overwrote `mock_llm.complete`, breaking failure-mode structural tests
**Symptom:** `test_empty_llm_response_returns_zero_keywords` and `test_llm_refusal_returns_zero_keywords` failed. The test set `mock_llm.complete = AsyncMock(return_value="")` before calling `_make_ctx`, but the agent still saw the standard 3-keyword response.

**Root cause:** `_make_ctx` unconditionally re-assigned `mock_llm.complete = AsyncMock(return_value=_MOCK_LLM_RESPONSE)`, overwriting whatever the test had set.

**Fix:** Removed the `mock_llm.complete` assignment from `_make_ctx`. The conftest fixture provides the default response; tests that need a different response set it on the mock before calling `_make_ctx`.

**Rule:** Helper functions that build fixtures must never override fields the caller has already set.

---

### Issue 12 — pytest did not discover `eval_*.py` files; collected 0 tests from `tests/evals/`
**Symptom:** `pytest tests/evals/` reported "no tests collected" even though `pytest tests/evals/seo/eval_keyword_research.py` collected 21 tests.

**Root cause:** pytest's default `python_files` glob is `test_*.py`. Eval files named `eval_*.py` are invisible to directory-based discovery.

**Fix:** Added to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
python_files = ["test_*.py", "eval_*.py"]
```

**Rule:** Any test file that doesn't start with `test_` needs the extra glob in `python_files`. Specifying the file path directly bypasses this — so `pytest path/to/file.py` works even without the config, masking the issue.

---

### Issue 13 — Two Alembic heads after adding evals_log migration
**Symptom:** `uv run alembic upgrade head` failed: "Multiple head revisions are present".

**Root cause:** The new migration used `down_revision = "d5e6f7a8b9c0"` (create_app_role). But `22619f407a67` (add_intent_reason_to_keywords) also points to `d5e6f7a8b9c0` as its parent. Two migrations with the same parent = two heads.

**Fix:** Updated `down_revision` in the new migration to `"22619f407a67"` (the true latest head at the time of creation).

**Rule:** Before writing a new migration, always run `uv run alembic heads` to identify the current head. Use that revision as `down_revision`, not one you remember from a previous session.

---

## API / Auth

### Issue 8 — Dashboard keywords page returned 404 "Organization not found"
**Symptom:** `POST /api/v1/keywords/research` returned HTTP 404 from the browser. Axios error: `Request failed with status code 404`. The route existed (confirmed via `/openapi.json`).

**Root cause:** The FastAPI `get_current_org` dependency in `deps.py` raises `HTTP_404_NOT_FOUND` when no `organizations` row matches the authenticated Supabase user's ID. The dev org (`00000000-0000-0000-0000-000000000001`) existed in the DB but had `supabase_user_id = NULL` — it was never linked to the actual Supabase account used for login.

**Fix:** Linked the dev org to the authenticated user:
```sql
UPDATE organizations
SET supabase_user_id = '<supabase-user-id-from-api-logs>'
WHERE id = '00000000-0000-0000-0000-000000000001';
```
The Supabase user ID appears in API logs whenever a token is verified: look for `WHERE organizations.supabase_user_id = $1` in SQLAlchemy debug output.

**Prevention:** The `scripts/seed_db.py` (or equivalent setup script) should seed a dev org with a known `supabase_user_id` matching the dev Supabase account, so new dev machines are immediately usable.

---

## Next.js / Vercel

### Issue 14 — Vercel build: `ENOENT (dashboard)/page_client-reference-manifest.js`
**Symptom:** Vercel deployment failed during "Tracing Next.js server files": `Error: ENOENT: no such file or directory, lstat '/vercel/path0/.next/server/app/(dashboard)/page_client-reference-manifest.js'`.

**Root cause:** Two pages mapped to the same `/` URL — `src/app/page.tsx` and `src/app/(dashboard)/page.tsx`. Next.js compiled `(dashboard)/page.tsx` into `(dashboard)/page.js` and wrote its `.nft.json` with a relative dep `page_client-reference-manifest.js`. But because route groups don't add a URL segment, the manifest was written to the root `app/page_client-reference-manifest.js`, not inside `(dashboard)/`. Vercel's file tracer walked `(dashboard)/page.js.nft.json`, tried to `lstat` `(dashboard)/page_client-reference-manifest.js`, and crashed.

**Fix:** Deleted `src/app/(dashboard)/page.tsx`. The root redirect is handled entirely by `src/app/page.tsx` (outside the route group). After this, `(dashboard)/` contains only its sub-routes, no `page.js` is emitted there, and every `.nft.json` manifest reference resolves to a file that actually exists.

**Rule:** Never have both `app/page.tsx` and `app/(group)/page.tsx` mapping to the same URL. The duplicate causes a silent manifest path mismatch that only surfaces in Vercel's file tracer, not in local builds.

---

## Docker / Integrations

### Issue 15 — docker-compose env_file: godotenv expands `\n` in JSON values
**Symptom:** `docker compose up -d` failed: `failed to read .env: line 30: unexpected character "\"" in variable name "\"type\": \"service_account\","`. When containers were recreated, `GSC_SERVICE_ACCOUNT_JSON` was only 45 chars (placeholder) instead of 2325 chars (real credentials).

**Root cause:** docker-compose v2 uses `godotenv` to parse `env_file:` entries. `godotenv` expands `\n` escape sequences even in unquoted values. The service account JSON contains `"private_key": "-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END"`. When godotenv hit `\n` inside the private key, it inserted a real newline, splitting the JSON. The next line started with `"type": "service_account",` which the parser tried to interpret as a variable name, failing with "unexpected character".

**Fix:** Wrapped the `GSC_SERVICE_ACCOUNT_JSON` value in single quotes in `.env`:
```
GSC_SERVICE_ACCOUNT_JSON='{"type":"service_account",...,"private_key":"-----BEGIN...\n...-----END\n",...}'
```
Single-quoted values in godotenv are 100% literal — no escape expansion. Both python-dotenv and docker-compose strip the surrounding quotes correctly, so all consumers see the raw JSON string.

**Rule:** Any `.env` value containing `\n`, `\"`, or other backslash sequences (e.g. JSON with a private key) must be wrapped in single quotes to survive docker-compose's godotenv parser. python-dotenv on the host handles either format.

---

### Issue 16 — `docker compose restart` doesn't re-read env_file; stale credentials baked into containers
**Symptom:** After updating `.env` with real GSC credentials, the container still showed `GSC_SERVICE_ACCOUNT_JSON` as a 45-char placeholder after `docker compose restart`.

**Root cause:** `docker compose restart` reuses the existing container configuration snapshot — it does not re-read `env_file:` or `environment:`. Env vars are only updated when a container is recreated (`up -d` or `up -d --force-recreate`).

**Fix:** Use `docker compose up -d` (after fixing any env_file format issues) to recreate containers and pick up new env var values. `restart` is only safe when you know the container config hasn't changed.

---

### Issue 17 — GSC API base URL deprecated: `www.googleapis.com/webmasters/v3` → 404
**Symptom:** All GSC API calls (`list_sites`, `get_search_analytics`) returned `403 Forbidden` or `404 Not Found`.

**Root cause:** The Google Search Console API migrated from `https://www.googleapis.com/webmasters/v3` (deprecated, now 404 on discovery) to `https://searchconsole.googleapis.com/webmasters/v3`. The integration used the old base URL.

**Fix:** Updated `_GSC_BASE` in `integrations/google_search_console.py`:
```python
_GSC_BASE = "https://searchconsole.googleapis.com/webmasters/v3"
```

---

### Issue 18 — GSC `health_check()` returning False: discovery URL also 404
**Symptom:** `health_check()` returned `False` even when the container had full internet access to Google.

**Root cause:** `health_check()` pinged `https://www.googleapis.com/discovery/v1/apis/webmasters/v3/rest` which also returns 404 (deprecated alongside the old base URL).

**Fix:** Changed health check to ping `https://oauth2.googleapis.com/token` with a GET request. This always returns HTTP 405 (Method Not Allowed) — never a 5xx or network error — confirming Google API reachability without credentials.

---

### Issue 19 — `google-auth` missing from Dockerfile.api despite being in pyproject.toml
**Symptom:** `from integrations.google_search_console import ...` raised `ModuleNotFoundError: No module named 'google'` inside the container.

**Root cause:** `apps/api/pyproject.toml` listed `google-auth>=2.29.0` as a dependency, but `infra/docker/Dockerfile.api` had a hardcoded `uv pip install` list that didn't include it. The two lists were out of sync.

**Fix:** Added `google-auth>=2.29.0` to the `uv pip install` list in `Dockerfile.api`. Rebuilt both `api` and `worker` images.

**Rule:** When adding a new Python dependency to `pyproject.toml`, always add it to `Dockerfile.api`'s `uv pip install` list in the same commit. They are manually kept in sync.

---

---

## trend_collector agent

### Issue 21 — pytrends is sync; blocks the event loop if called directly in async execute()
**Symptom:** Calling `TrendReq(...).interest_over_time()` directly inside an `async def execute()` blocks the entire asyncio event loop for the duration of the HTTP request to Google Trends (~1-3 seconds per batch).

**Root cause:** pytrends uses the `requests` library internally, which is synchronous. Calling blocking I/O directly in an async function stalls all other coroutines until it returns.

**Fix:** Wrap each pytrends batch call with `asyncio.get_running_loop().run_in_executor(None, _fetch_trends_sync, ...)`. This offloads the blocking call to a thread pool worker, letting the event loop remain responsive. The function itself is a plain sync function (no async).

**Rule:** Any third-party library that uses `requests` (not `httpx`/`aiohttp`) must be called via `run_in_executor` in async agents. The fallback path (neutral 5.0 momentum on any exception) ensures pytrends rate-limit errors never fail the agent.

---

## competitor_monitor agent / SitemapIntegration

### Issue 22 — ElementTree element truth-value falsy for leaf nodes; `or` fallback swallowed namespace-qualified finds
**Symptom:** `_parse_sitemap_xml` returned `[]` for any sitemap that used the standard `xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"` namespace. Non-namespaced sitemaps parsed correctly.

**Root cause:** The parser used `child.find(f"{{{ns}}}loc") or child.find("loc")` to handle both namespaced and non-namespaced XML. `child.find(f"{{{ns}}}loc")` correctly returned a `<loc>` element, but Python's `or` evaluated the element's truth value. In `xml.etree.ElementTree`, leaf elements (no subelement children) have falsy truth values — `<loc>https://...</loc>` has no child elements so `bool(element)` returned `False`. The `or` then fell through to `child.find("loc")` (no namespace), which returned `None` since the tag is namespaced. Result: every `loc_el` was `None`, no URLs collected.

**Fix:** Replace boolean `or` with explicit `is None` check:
```python
loc_el = child.find(f"{{{ns}}}{loc_tag}")
if loc_el is None:
    loc_el = child.find(loc_tag)
```

Same fix for `children`: `root.findall(f"{{{ns}}}{child_tag}")` returns a list (always truthy or empty), so `if not children:` is safe for the list-level fallback.

**Rule:** Never test XML elements with boolean operators (`or`, `not`, `if element`). Always use `element is None` / `element is not None`. Python raises `DeprecationWarning` now; future versions will always return `True` which would break the fallback logic in the opposite direction.

---

### Issue 23 — Lazy import inside try-block breaks `patch()` in unit tests
**Symptom:** `patch("agents.knowledge.rag_searcher.EmbeddingGenerator", ...)` raised `AttributeError: module 'agents.knowledge.rag_searcher' has no attribute 'EmbeddingGenerator'`, even though the import worked fine at runtime.

**Root cause:** `EmbeddingGenerator` was imported inside a `try` block at the start of `execute()`:
```python
try:
    from rag.embeddings import EmbeddingGenerator
    embedding = await EmbeddingGenerator().generate_one(query)
```
`patch()` replaces the attribute on the *module object* (`agents.knowledge.rag_searcher.EmbeddingGenerator`). A lazy/local import never sets that attribute, so the patch target doesn't exist at test time.

**Fix:** Move the import to module level (top of file):
```python
from rag.embeddings import EmbeddingGenerator  # must be module-level for patch() to work
```

**Rule:** Any symbol you intend to `patch()` in tests must be imported at module level. Lazy imports inside functions or `try` blocks are invisible to `patch()`. This applies to all agents using `EmbeddingGenerator`, `TrendReq`, or any optional dependency.

---

### Issue 24 — asyncpg named-param parser breaks on `::vector` / `::jsonb` type casts
**Symptom:** SQL containing `CAST(:param AS vector)` worked; `embedding <=> :query_vec::vector` raised a parse error or silently failed with asyncpg.

**Root cause:** asyncpg uses `:param` syntax for named parameters. When a query contains `::vector`, asyncpg's parser sees the `::` prefix and interprets it as part of a parameter name, breaking the entire query parse.

**Fix:** Always use `CAST(:param AS vector)` instead of `:param::vector`. Same for `::jsonb` → `CAST(:param AS jsonb)`.

```python
# WRONG (breaks asyncpg):
"1 - (embedding <=> :query_vec::vector)"

# CORRECT:
"1 - (embedding <=> CAST(:query_vec AS vector))"
```

**Rule:** Never use PostgreSQL's `::type` cast syntax in any SQL that passes through asyncpg with named parameters. Always use `CAST(... AS type)`.

---

### Issue 20 — GSC 403 means "API not enabled in GCP", not "permission denied on property"
**Symptom:** After fixing the base URL and loading real credentials, `list_sites()` still returned `403 Forbidden`.

**Root cause:** The error body (only visible by printing `response.text`) read: *"Google Search Console API has not been used in project 500830108778 before or it is disabled."* The service account credentials were valid and the token was issued, but the Search Console API was never enabled in the GCP project.

**Fix:** Enable the API at: `https://console.developers.google.com/apis/api/searchconsole.googleapis.com/overview?project=<project-number>`

**Diagnosis tip:** A 403 from a Google API almost always means one of: (a) API not enabled, (b) service account not authorized on the resource, or (c) quota exceeded. Always print `response.text` — the JSON body distinguishes these cases immediately. Never treat a 403 as just "permissions" without reading the error body.

---

## EmailIntegration / video_handoff

### Issue 25 — smtplib blocks the asyncio event loop if called directly in async code
**Symptom:** Calling `smtplib.SMTP(...)` inside `async def` stalls all other coroutines during the TCP handshake + TLS negotiation + AUTH sequence (~300–600 ms per send).

**Root cause:** `smtplib` is synchronous (uses stdlib `socket`). Calling it from `async def` blocks the thread the event loop runs on.

**Fix:** Wrap in `run_in_executor`. Keep the actual SMTP work in a plain sync method `_send_sync`; call it as `await loop.run_in_executor(None, self._send_sync, to, subject, body_html)`.

**Rule:** Any stdlib or third-party library using synchronous I/O (smtplib, requests, pytrends) must be wrapped in `run_in_executor`. Same pattern as pytrends in trend_collector (Issue 21).

---

### Issue 26 — patch() on keyword-arg calls: call_args[0] is empty tuple
**Symptom:** `mock_send.call_args[0][1]` raised `IndexError: tuple index out of range` even though `mock_send` was clearly called.

**Root cause:** Agent called `email.send_email(to=..., subject=..., body_html=...)` using all keyword arguments. `call_args[0]` holds positional args — empty here. Values are in `call_args.kwargs`.

**Fix:** Use `mock.call_args.kwargs["subject"]` / `mock.call_args.kwargs["body_html"]` when production code uses keyword arguments.

**Rule:** Before writing test assertions against `call_args`, check whether the call site uses positional or keyword args. Use `call_args[0]` for positional, `call_args.kwargs` for keyword.

---

### Issue 27 — asyncpg cannot cast named params to ::vector type
**Symptom:** `asyncpg.exceptions.DataError: invalid input for query argument $1: expected str, got list` when trying to pass an embedding list as a named param and cast with `CAST(:embedding AS vector)`.

**Root cause:** asyncpg cannot bind Python list/tuple values to PostgreSQL custom types like `vector`. Named parameter binding only works for scalar types.

**Fix:** Build the vector literal inline in the SQL string using Python f-string: `f"'[{','.join(str(x) for x in embedding)}]'::vector"`. This embeds the vector value directly as a SQL literal rather than a bound parameter. For NULL embeddings (on failure), use standard `NULL` literal.

**Rule:** Never try to bind embeddings (or other custom PostgreSQL types) as named params. Interpolate them directly into the SQL string after validating the data shape.

---

### Issue 28 — `params or {...}` treats empty dict {} as falsy in test helpers
**Symptom:** `test_missing_opportunity_id_fails` passed the agent empty params `{}` but the agent succeeded because the test helper `ctx.params = params or {"opportunity_id": OPP_ID}` replaced `{}` with defaults.

**Root cause:** Empty dict `{}` is falsy in Python. `params or {...}` substitutes the default when `params={}` is intentional.

**Fix:** Change `params or {"opportunity_id": OPP_ID}` to `{"opportunity_id": OPP_ID} if params is None else params`. This only substitutes defaults when `params` is explicitly `None`, not when it's an empty dict.

**Rule:** In test `_ctx()` helpers, always use `if params is None else params` rather than `or {}` to avoid the falsy-empty-dict trap.

---

### Issue 29 — contracts.py forward-reference alias broke import
**Symptom:** `NameError: name 'ArticlePlannerOutput' is not defined` at import time when code at the top of contracts.py had `ArticlePlanOutput = ArticlePlannerOutput` before the class was defined at the bottom of the file.

**Root cause:** Module-level assignment runs top-to-bottom at import time. The alias was created before the class definition was reached.

**Fix:** Removed the premature alias and replaced it with a comment `# ArticlePlannerOutput defined later in this file`. Any code that needed the alias was updated to import the real class directly.

**Rule:** Never create module-level aliases for classes that are defined later in the same file. Either define the class first, or use `TYPE_CHECKING` blocks.

---

### Issue 31 — TypeScript: `Promise<T>` not assignable to `Promise<void>` in mutation callback props

**Symptom:** `src/app/(dashboard)/competitors/page.tsx(157,51): error TS2322: Type 'Promise<Competitor>' is not assignable to type 'Promise<void>'. Type 'Competitor' is not assignable to type 'void'`.

**Root cause:** `AddCompetitorForm` declared its `onAdd` prop as `(domain: string) => Promise<void>`. The call site passed `(domain) => addMutation.mutateAsync(domain)`, which returns `Promise<Competitor>`. TypeScript requires an exact return type match on the prop.

**Fix:** Chain `.then(() => {})` at the call site to discard the resolved value: `(domain) => addMutation.mutateAsync(domain).then(() => {})`. This converts `Promise<Competitor>` to `Promise<void>` without changing the prop type.

**Alternative:** Widen the prop type to `(domain: string) => Promise<unknown>` or `Promise<void | Competitor>`, but the `.then()` approach is less invasive.

**Rule:** When a component prop declares `() => Promise<void>` and the caller passes a TanStack mutation's `mutateAsync`, always chain `.then(() => {})` to drop the typed return value.

---

### Issue 30 — video_scripts scenes column needed ::jsonb CAST for asyncpg
**Symptom:** `asyncpg.exceptions.DataError: invalid input for query argument` when inserting JSON string for the `scenes` JSONB column.

**Root cause:** asyncpg doesn't auto-cast Python strings to JSONB. The `CAST(:scenes AS jsonb)` pattern is required for all JSONB columns when using named parameters.

**Fix:** Use `CAST(:scenes AS jsonb)` in the INSERT statement for all JSONB columns (scenes, tweets, recommendations). This pattern was already established for `twitter_threads` and applied consistently to `video_scripts` and `strategy_reports`.

**Rule:** Every JSONB column in an INSERT/UPDATE statement must use `CAST(:param AS jsonb)` when binding via named parameters in asyncpg.

---

## CI / GitHub Actions

### Issue 32 — ruff auto-fix changes not committed; CI saw unfixed code

**Symptom:** CI lint job failed with E501/I001/F401 errors after `uv run ruff check apps/api/` passed locally.

**Root cause:** Running `uv run ruff check apps/api/ --fix` locally fixed the files on disk but those changes were never staged or committed. The local working tree showed "all checks passed" because the fixed files were present. CI checked out the last committed version, which still had the original unfixed code.

**Fix:** After running `ruff --fix`, always run `git add -p` (or `git status` + `git add`) to stage the auto-fixed files, then commit them before pushing.

---

## Frontend / UI

### BUG-UI-003 — brand_voice_keeper: style_rules and target_audience fields missing from Settings page

**Agent:** brand_voice_keeper  
**Layer:** C — UI  
**Check:** C2 Form fields  
**Severity:** Medium  
**Discovered:** 2026-05-06 via test harness UI checklist review  

**Symptom:** The `/settings` Brand Voice form does not expose the `style_rules` object or a `target_audience` field. Users who want to set style rules (e.g. `max_sentence_length`, `prefer_active_voice`, `oxford_comma`) or specify a target audience have no way to do so through the UI. The values can only be written via the CLI or direct API call.

**Root cause:** The `brand_voice` DB schema stores `style_rules` as a JSONB object with arbitrary keys, and the `BrandVoiceKeeperAgent` accepts `style_rules` as a parameter. However, the Settings page component (`apps/web`) was built with only `tone`, `vocabulary`, and `banned_phrases` form fields. The `style_rules` key was known at design time but deferred as a "later" addition and never implemented. `target_audience` is not a current DB column — it would need a migration if added.

**Impact:**
- `style_rules` values set via CLI/API are **not corrupted** on UI save — the `PUT /api/v1/brand-voice` handler uses `if body.style_rules is not None` guard, so omitting style_rules from the request body preserves the existing DB value silently.
- Users have no visibility into which style rules are currently active — they cannot read them from the UI.
- Users cannot edit style rules from the UI — the only paths are CLI agent run or direct API call.
- Any content agent that reads `style_rules` for prompt injection receives empty rules for orgs that have only ever used the UI (since they've never been able to set them).

**Fix required:**
1. `apps/web` — Add `style_rules` as an editable key-value section in the Brand Voice settings form. Each style rule should be an add/remove pair (key + value). Use the `PUT /api/v1/brand-voice` endpoint — it already accepts `style_rules`.
2. Decide whether `target_audience` is a first-class column (requires Alembic migration + agent param support) or a key inside `style_rules` (no migration needed — just a convention). Add the corresponding form field once decided.
3. Ensure the PUT handler merges incoming `style_rules` with existing ones (currently it replaces entirely on PUT — verify this is acceptable).

**UI checklist items added to brand_voice_keeper config:**
- `[ ] Style rules section renders key-value pairs, not raw JSON blob`
- `[ ] Target audience field is visible`
- `[ ] Target audience accepts free text`

**Status:** Open — fix not yet implemented.

---

### Issue 33 — `anyio.Path` return type breaks pyright: not a subclass of `pathlib.Path`

**Symptom:** After replacing `pathlib.Path.mkdir()` with `await anyio.Path(...).mkdir()` to fix ASYNC240, pyright reported: `"anyio._core._fileio.Path" is not assignable to "pathlib.Path" (reportReturnType)` on the `return dest` line.

**Root cause:** ASYNC240 flags `pathlib.Path` methods that perform blocking I/O (`.mkdir()`, `.open()`, `.read_bytes()`, `.write_bytes()`). The fix was incorrectly applied to pure string operations too: `suffix = anyio.Path(video.filename).suffix` and `dest = anyio.Path(_UPLOAD_DIR) / f"{job_id}{suffix}"`. This made `dest` an `anyio.Path`, which is NOT a subclass of `pathlib.Path` (its MRO is `anyio.Path → object`). The function was annotated `-> Path` (pathlib), so pyright rejected the return.

**Fix:** Only wrap the specific I/O call in `anyio.Path`:
```python
await anyio.Path(_UPLOAD_DIR).mkdir(parents=True, exist_ok=True)   # ← anyio, async I/O
suffix = Path(video.filename or "video.mp4").suffix or ".mp4"       # ← pathlib, pure string op
dest = _UPLOAD_DIR / f"{job_id}{suffix}"                            # ← pathlib, pure path op
```

**Rule:** ASYNC240 only applies to I/O methods (`.mkdir`, `.open`, `.read_*`, `.write_*`). Property accesses (`.suffix`, `.name`) and path arithmetic (`/`) are safe to call on `pathlib.Path` in async functions. Do NOT convert these to `anyio.Path` — it changes the type and breaks return type annotations.

---

### Issue 34 — `WordPressIntegration` could not be instantiated: missing abstract method

**Symptom:** `pyright apps/api/` reported: `Cannot instantiate abstract class "WordPressIntegration"` on the line `return WordPressIntegration(site_url=..., username=..., app_password=...)`.

**Root cause:** `BaseIntegration` (in `integrations/base.py`) declares two abstract methods: `health_check()` and `get_credentials()`. `WordPressIntegration` implemented `health_check()` but not `get_credentials()`. Any class with an unimplemented `@abstractmethod` is treated as abstract by both Python and pyright — it cannot be instantiated.

**Fix:** Added a stub implementation to `WordPressIntegration`:
```python
async def get_credentials(self, org_id: str, db: Any) -> dict:
    return {}
```
WordPress credentials come from env vars, not the DB, so the stub correctly returns an empty dict (same pattern as `SlackWebhookIntegration`).

**Rule:** Every concrete subclass of `BaseIntegration` must implement ALL abstract methods: `health_check()` AND `get_credentials()`. When adding a new integration, implement both even if `get_credentials` is a no-op stub.

---

### Issue 35 — `Mapped[dict]` on JSONB array column caused pyright assignment error

**Symptom:** pyright reported: `Type "list[str]" is not assignable to type "SQLCoreOperations[dict] | dict"` when setting `bv.vocabulary = body.vocabulary` in the brand voice update endpoint.

**Root cause:** `BrandVoice.vocabulary` and `BrandVoice.banned_phrases` were declared `Mapped[dict]` in the ORM model, but their `server_default` is `'[]'::jsonb` (a JSON array, not an object). The API body schema correctly types them as `list[str]`. The mismatch was in the model: `dict` (JSON object) vs `list` (JSON array).

**Fix:** Changed the ORM column type annotations from `Mapped[dict]` to `Mapped[list]`:
```python
vocabulary: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"), ...)
banned_phrases: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"), ...)
```

**Rule:** Match the `Mapped[...]` type to the actual JSON shape stored in the column. `'[]'::jsonb` default → `Mapped[list]`. `'{}'::jsonb` default → `Mapped[dict]`. A mismatch is invisible at runtime (PostgreSQL accepts both) but pyright catches it at type-check time.

---

### Issue 37 — `python-multipart` missing; FastAPI crashes at startup on any file/form endpoint

**Symptom:** `RuntimeError: Form data requires "python-multipart" to be installed` — API container starts uvicorn but crashes immediately when FastAPI tries to register any route that uses `UploadFile`, `File()`, or `Form()`.

**Root cause:** FastAPI does not bundle a multipart parser. It calls `ensure_multipart_is_installed()` at route registration time (not at request time), so the error happens on startup, not on the first upload request. `python-multipart` was not in `apps/api/pyproject.toml` or `Dockerfile.api`.

**Fix:** Added `"python-multipart>=0.0.9"` to both `apps/api/pyproject.toml` and the `uv pip install` list in `infra/docker/Dockerfile.api`. Rebuilt and restarted the container.

**Rule:** Any FastAPI app with `UploadFile`, `File()`, or `Form()` parameters requires `python-multipart`. Add it when writing the first such endpoint. Also note: the Dockerfile has a hardcoded install list separate from `pyproject.toml` — keep them in sync whenever adding a new dependency to either.

---

### Issue 36 — `pypdf` and `python-docx` missing from `pyproject.toml`; pyright `reportMissingImports`

**Symptom:** CI type-check failed: `Import "pypdf" could not be resolved` and `Import "docx" could not be resolved` in `document_ingester.py`.

**Root cause:** `document_ingester.py` imports `pypdf` and `docx` (from `python-docx`) inside helper functions as lazy imports. They were installed in the local dev environment but never added to `apps/api/pyproject.toml`. CI installs dependencies from `pyproject.toml` (`pip install -e apps/api`), so the packages were absent and pyright couldn't resolve the imports.

**Fix:** Added to `apps/api/pyproject.toml` `[project] dependencies`:
```toml
"pypdf>=4.0.0",
"python-docx>=1.1.0",
"anyio>=4.4.0",
```
(`anyio` was already a transitive dependency via FastAPI/Starlette but added explicitly since `video_upload.py` uses it directly.)

**Rule:** Any `import X` in the codebase — including lazy imports inside functions — must have the corresponding package in `apps/api/pyproject.toml`. Add the dependency in the **same commit** as the import. Never rely on transitive installs for packages you import directly.

---

## Competitors page — UI bugs (found 2026-05-06, competitor_monitor test harness)

### BUG-UI-005 — Domain stored with https:// prefix

**Agent:** competitor_monitor  
**Layer:** C — UI / B — API  
**Severity:** Medium  
**Status:** ✅ FIXED

**Symptom:** Adding `https://monday.com` stored `https://monday.com` in DB instead of `monday.com`. Duplicate check then failed because `https://monday.com` ≠ `monday.com`.

**Root cause:** `handleSubmit` in `AddCompetitorForm` stripped `https://` but did not strip `www.` or path components. Existing rows in DB had inconsistent formats.

**Fix:**
- Added `normaliseDomain()` function: strips protocol, `www.`, and any path components.
- Applied to form submit before API call.
- Cleaned existing dirty rows in DB via `regexp_replace`.

---

### BUG-UI-006 — Duplicate competitors not detected

**Agent:** competitor_monitor  
**Layer:** C — UI  
**Severity:** Medium  
**Status:** ✅ FIXED

**Symptom:** Adding the same domain twice (e.g. once as `https://monday.com`, once as `monday.com`) showed no warning — both attempts hit the API, and the server returned a conflict which surfaced as a generic error, not a user-facing duplicate message.

**Root cause:** No client-side duplicate check before the API call. Normalisation mismatch compounded the problem.

**Fix:**
- `AddCompetitorForm` now receives `existingDomains` prop (list of normalised domains from current query state).
- Before submitting, normalises input and checks against `existingDomains`.
- Shows inline message: `"{domain} is already being tracked."` — no API call made.

---

### BUG-UI-009 — No crawl status indicator in competitors list

**Agent:** competitor_monitor  
**Layer:** C — UI  
**Severity:** Low  
**Status:** ✅ FIXED

**Symptom:** "Last Crawled" column showed raw `timeAgo()` string or "never" — no visual distinction between domains that had been crawled vs never crawled.

**Root cause:** Column was plain text with no styling or status semantics.

**Fix:**
- Added `CrawlStatus` component: green dot + "Done · {time ago}" when crawled; grey "Never crawled" when `last_crawled_at` is null.
- Renamed column header "Last Crawled" → "Status".
- Added `crawl_status VARCHAR(20) DEFAULT 'never'` column via Alembic migration `g0h1i2j3k4l5` (reserved for future real-time queue status; UI derives display from `last_crawled_at` for now).

---

### BUG-UI-010 — Content tab empty state not distinguishing no-data vs no-search-match

**Agent:** competitor_monitor  
**Layer:** C — UI  
**Severity:** Low  
**Status:** ✅ FIXED

**Symptom:** Content tab showed a single empty message regardless of whether the org had no extracted content at all, or whether a search filter had no matches.

**Fix:**
- Two distinct empty states:
  - `competitorContent.length === 0` → "No competitor content extracted yet. Run competitor monitor to start crawling."
  - `filteredContent.length === 0` (search active, data exists) → "No results match your search."
- Tab switch now resets `contentSearch` to `''` so content tab always opens unfiltered.

---

## Keywords page — UI bugs (found 2026-05-06, Layer 3 keyword_research testing)

### BUG-UI-013 — Duplicate keyword rows in DB and table

**Layer:** A — Agent / C — UI  
**Severity:** Medium  
**Status:** ✅ FIXED

**Symptom:** Same keyword text appeared multiple times in the keywords table (e.g. "project management software reviews" × 3). Each agent run inserted fresh rows regardless of whether the keyword already existed.

**Root cause:** `keywords` table had no unique constraint on `(org_id, keyword)`. The `ON CONFLICT DO NOTHING` in the INSERT referred only to the primary key (UUID), so every run created a new row.

**Fix:**
- Deleted 14 duplicate rows (kept earliest `created_at` per `org_id + keyword` pair).
- Added `UNIQUE (org_id, keyword)` constraint via Alembic migration `h1i2j3k4l5m6` (includes dedup logic in the migration body).
- Updated `keyword_research.py` INSERT: `ON CONFLICT DO NOTHING` → `ON CONFLICT (org_id, keyword) DO NOTHING` so the explicit conflict target is clear.

---

### BUG-UI-016 — KD colour thresholds missing orange tier

**Layer:** C — UI  
**Severity:** Low  
**Status:** ✅ FIXED

**Symptom:** `Difficulty` component (KeywordsTable.tsx) only had three bands: green / amber / red. No orange tier. KD 4 was showing green (boundary was `<= 4`, should be `< 4`).

**Fix:** Updated colour logic in `Difficulty` component:
- `KD < 4` → green (`#16A34A` / `text-green-700`)
- `KD 4–<7` → yellow (`#CA8A04` / `text-yellow-700`)
- `KD 7–9` → orange (`#EA580C` / `text-orange-600`)
- `KD > 9` → red (`#DC2626` / `text-red-700`)

---

### BUG-UI-017 — Agent runs always displayed green; no last-success indicator

**Layer:** C — UI  
**Severity:** Low  
**Status:** ✅ FIXED

**Symptom:** `KeywordDrawer` showed all agent run rows with a green badge regardless of actual status. A failed run looked identical to a successful one. No way to tell at a glance whether data was still valid.

**Fix:**
- Added "Last successful: {time ago}" banner in green above the runs list (only shown if at least one success/partial run exists).
- Run badge now uses status: `success|partial` → green dot; all other statuses → grey dot + grey text. Failed runs are never shown in red (they're informational, not alarming — data persists from prior successful run).

---

### BUG-API-001 — No domain validation on add competitor; unreachable domains accepted

**Agent:** competitor_monitor  
**Layer:** B — API  
**Severity:** Medium  
**Status:** ✅ FIXED

**Symptom:** `POST /api/v1/competitors` accepted any string as a domain — including nonexistent domains (`notareal-domain-xyz123.com`), bare labels (`not-a-domain`), and garbage strings. Invalid rows accumulated in the `competitors` table and the agent then tried to crawl them on every run.

**Root cause:** `add_competitor` only stripped protocol prefix and checked for empty string. No format validation, no DNS check.

**Fix:**
1. Regex format check — `_DOMAIN_RE` requires valid hostname characters with at least one dot and a real TLD.
2. Async DNS resolution — `_domain_resolves()` calls `loop.getaddrinfo()`. If the domain doesn't resolve, returns 422 with `"'{domain}' could not be resolved — check the domain and try again"`.
3. DB unique constraint violation now returns 409 instead of an unhandled 500.
4. `api.ts` — added axios response interceptor that extracts FastAPI `detail` field and sets it as `Error.message`, so frontend `catch` blocks see the human-readable server message.
5. DB cleanup: deleted `notareal-domain-xyz123.com` row that was already stored.

**Error responses:**
- Bad format → 422 `"'{domain}' is not a valid domain name"`
- No DNS → 422 `"'{domain}' could not be resolved — check the domain and try again"`
- Duplicate → 409 `"'{domain}' is already being tracked"`

---
