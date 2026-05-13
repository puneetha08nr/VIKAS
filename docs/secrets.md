# GitHub Actions Secrets

All secrets are set under **Settings → Secrets and variables → Actions** in the GitHub repo.

## Infrastructure / deploy

| Secret | Description | Example |
|---|---|---|
| `SERVER_HOST` | Production server IP or hostname | `203.0.113.10` |
| `SERVER_USER` | SSH user on the server | `ubuntu` |
| `SERVER_SSH_KEY` | Private SSH key for the server | `-----BEGIN OPENSSH PRIVATE KEY-----…` |
| `SERVER_PORT` | SSH port (usually 22) | `22` |
| `DEPLOY_DIR` | Absolute path to deploy directory | `/opt/vikas` |
| `DOCKER_USERNAME` | Docker Hub username | `elytsllc` |
| `DOCKERHUB_TOKEN` | Docker Hub access token | `dckr_pat_…` |

## Database

### URL format

```
# Runtime API (RLS enforced via vikas_app role)
DATABASE_URL=postgresql+asyncpg://vikas_app:<PASSWORD>@<HOST>:<PORT>/vikas

# Alembic migrations only (superuser / doadmin — bypasses RLS)
ADMIN_DATABASE_URL=postgresql+asyncpg://doadmin:<DOADMIN_PASSWORD>@<HOST>:<PORT>/vikas
```

On **DigitalOcean Managed PostgreSQL** the host looks like
`db-vikas-do-user-XXXXX-0.g.db.ondigitalocean.com` and the port is `25060`.
Copy the full connection string from the database dashboard and convert the
scheme from `postgresql://` to `postgresql+asyncpg://`.

### vikas_app password

`vikas_app` is created by migration `d5e6f7a8b9c0` as a **NOLOGIN role** — it has no
password in the migrations. Before the application can connect as `vikas_app` you must
run these two SQL commands once on the production database (connect as `doadmin`):

```sql
ALTER ROLE vikas_app LOGIN;
ALTER ROLE vikas_app PASSWORD 'your-strong-password-here';
```

Then set that same password in the `DATABASE_URL` secret above.

> **Local dev default** — `settings.py` has `database_url: str = ""` (empty).
> There is no localhost fallback baked in. Set `DATABASE_URL` in `.env` before
> starting the API. The docker-compose dev stack creates the role as a login user
> with password `vikas_app_dev` (see `docker-compose.yml` init SQL).

### GitHub Action secrets

| Secret | Description |
|---|---|
| `DATABASE_URL` | asyncpg URL for `vikas_app` (RLS-enforced, runtime only) |
| `ADMIN_DATABASE_URL` | asyncpg URL for `doadmin` (Alembic migrations only; never used by the API at runtime) |

## Auth (Supabase)

| Secret | Description | Example |
|---|---|---|
| `SUPABASE_URL` | Supabase project URL | `https://xyzxyz.supabase.co` |
| `SUPABASE_ANON_KEY` | Public anon key (frontend) | `eyJ…` |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key (backend admin) | `eyJ…` |
| `SUPABASE_JWT_SECRET` | JWT secret for local token verification — **Project Settings → API → JWT Secret** | `your-super-secret-jwt-token` |

The web build also needs these as build args (already wired in deploy.yml):

| Secret | Description |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Same as `SUPABASE_URL` — exposed to browser |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Same as `SUPABASE_ANON_KEY` — exposed to browser |

## Encryption

| Secret | Description | How to generate |
|---|---|---|
| `SETTINGS_ENCRYPTION_KEY` | Fernet key for encrypting per-org integration credentials in DB | `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

## LLM Providers

| Secret | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key (`sk-…`) |
| `ANTHROPIC_API_KEY` | Anthropic API key (`sk-ant-…`) |
| `GEMINI_API_KEY` | Google AI / Gemini API key |
| `OPENROUTER_API_KEY` | OpenRouter key (fallback provider) |

## Storage (AWS S3)

| Secret | Description |
|---|---|
| `AWS_ACCESS_KEY_ID` | IAM access key with S3 read/write on `vikas-media` bucket |
| `AWS_SECRET_ACCESS_KEY` | Corresponding secret key |

## Notifications

| Secret | Description |
|---|---|
| `SLACK_WEBHOOK_URL` | Incoming webhook URL for agent failure alerts |
| `SMTP_HOST` | SMTP server hostname (e.g. `smtp.sendgrid.net`) |
| `SMTP_USER` | SMTP username |
| `SMTP_PASSWORD` | SMTP password or API key |
| `VIDEO_TEAM_EMAIL` | Email address for video handoff notifications |

## Search & Social APIs

| Secret | Description |
|---|---|
| `GOOGLE_SEARCH_API_KEY` | Google Custom Search API key |
| `GOOGLE_SEARCH_CX` | Custom Search Engine ID |
| `NEWSAPI_KEY` | NewsAPI.org key (trend_collector) |
| `YOUTUBE_API_KEY` | YouTube Data API v3 key |

## Google Search Console (GSC)

| Secret | Description |
|---|---|
| `GSC_SERVICE_ACCOUNT_JSON` | Service account JSON (minified — no newlines). Grant it "Verified Owner" in GSC. |
| `GSC_SITE_URL` | Property URL e.g. `https://vikasai.elyts.tech/` |
| `GSC_CLIENT_ID` | OAuth client ID (if using OAuth flow instead of service account) |
| `GSC_CLIENT_SECRET` | OAuth client secret |
| `GSC_REFRESH_TOKEN` | OAuth refresh token |

> **Note**: `GSC_SERVICE_ACCOUNT_JSON` and `GA4_SERVICE_ACCOUNT_JSON` must be stored as minified (single-line) JSON. Multi-line JSON will break `.env` parsing. Use `jq -c . service-account.json` to minify before pasting.

## Google Analytics 4 (GA4)

| Secret | Description |
|---|---|
| `GA4_PROPERTY_ID` | Numeric GA4 property ID (e.g. `123456789`) |
| `GA4_SERVICE_ACCOUNT_JSON` | Service account JSON (minified — no newlines) |

## WordPress

| Secret | Description |
|---|---|
| `WORDPRESS_URL` | WordPress site URL (e.g. `https://vikasai.elyts.tech`) |
| `WORDPRESS_APP_PASSWORD` | Application password from Users → Profile in WP admin |

## SEO APIs

| Secret | Description |
|---|---|
| `AHREFS_API_KEY` | Ahrefs API key |
| `DATAFORSEO_LOGIN` | DataForSEO account login (email) |
| `DATAFORSEO_PASSWORD` | DataForSEO account password |
