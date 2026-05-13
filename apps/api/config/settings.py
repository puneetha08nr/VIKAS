from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Walk up from this file to find the repo-root .env so alembic works
# regardless of which directory it is invoked from.
_HERE = Path(__file__).resolve().parent
_ENV_FILE = next(
    (p / ".env" for p in [_HERE, *_HERE.parents] if (p / ".env").exists()),
    ".env",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=(),
    )

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = ""   # required in production via DATABASE_URL env var
    admin_database_url: str = ""  # vikas_admin — DDL privileges (Alembic only; optional at runtime)
    redis_url: str = "redis://localhost:6379/0"

    # ── App ───────────────────────────────────────────────────────────────────
    env: str = "development"
    log_level: str = "DEBUG"
    daily_cost_limit_usd: float = Field(default=50.0, alias="DAILY_COST_LIMIT_USD")
    cors_origins: list[str] = ["http://localhost:3000"]
    base_url: str = "http://localhost:8000"  # public base URL for generated links

    # ── LLM providers ─────────────────────────────────────────────────────────
    llm_provider: str = "ollama"   # ollama | google | anthropic | openai
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # ── Mock mode — set MOCK_LLM=false in .env to enable real API calls ───────
    mock_llm: bool = False

    # ── Auth ──────────────────────────────────────────────────────────────────
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    # Set DEV_AUTH_BYPASS=true to skip Supabase verification in local dev
    dev_auth_bypass: bool = False

    # ── Encryption ────────────────────────────────────────────────────────────
    # Generate with: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # noqa: E501
    settings_encryption_key: str = ""

    # ── Storage ───────────────────────────────────────────────────────────────
    s3_bucket: str = "vikas-media"
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # ── Notifications ─────────────────────────────────────────────────────────
    slack_webhook_url: str = ""
    slack_alert_channel: str = "#vikas-alerts"

    # ── Email / SMTP ──────────────────────────────────────────────────────────
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    video_team_email: str = ""
    admin_email: str = ""          # receives lead + chat notifications
    smtp_from_address: str = ""    # sender address (e.g. noreply@yourdomain.com)

    # ── Integrations ──────────────────────────────────────────────────────────
    gsc_service_account_json: str = ""
    gsc_site_url: str = ""
    gsc_client_id: str = ""
    gsc_client_secret: str = ""
    gsc_refresh_token: str = ""
    ga4_property_id: str = ""
    ga4_service_account_json: str = ""
    wordpress_url: str = ""
    wordpress_app_password: str = ""
    ahrefs_api_key: str = ""
    dataforseo_login: str = ""
    dataforseo_password: str = ""

    @property
    def is_dev(self) -> bool:
        return self.env == "development"


settings = Settings()
