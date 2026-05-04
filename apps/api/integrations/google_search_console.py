"""Google Search Console integration.

Set USE_MOCK_DATA=true in .env to return canned search analytics without
hitting the real API — useful while GSC has no traffic data yet.

Uses OAuth 2.0 user credentials (refresh token) via google-api-python-client.

Credential resolution order (first wins):
  1. org settings JSON blob — production path (org_id + db provided)
  2. GSC_CLIENT_ID / GSC_CLIENT_SECRET / GSC_REFRESH_TOKEN env vars — dev / CLI path

Setup (run once):
    python scripts/gsc_auth.py
Then add GSC_CLIENT_ID, GSC_CLIENT_SECRET, GSC_REFRESH_TOKEN to .env.
"""
import logging
import os
from datetime import date
from typing import Any

import httpx

from integrations.base import BaseIntegration, IntegrationError

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


class GoogleSearchConsoleIntegration(BaseIntegration):
    name = "google_search_console"
    base_url = "https://searchconsole.googleapis.com"
    max_requests_per_minute = 200

    # ── Auth ──────────────────────────────────────────────────────────────────

    async def get_credentials(
        self,
        org_id: str | None = None,
        db: Any | None = None,
    ) -> dict:
        """Satisfy BaseIntegration abstract contract. Returns OAuth token fields as dict."""
        org_settings = None
        if org_id and db:
            org_settings = await self._get_org_settings(org_id, db)
        creds = self._get_credentials(org_settings)
        return {
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "refresh_token": creds.refresh_token,
            "token": creds.token,
            "token_uri": creds.token_uri,
        }

    def _get_credentials(self, org_settings: dict | None = None):
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from config.settings import settings

        if org_settings:
            client_id = org_settings.get("gsc_client_id") or settings.gsc_client_id
            client_secret = org_settings.get("gsc_client_secret") or settings.gsc_client_secret
            refresh_token = org_settings.get("gsc_refresh_token") or settings.gsc_refresh_token
        else:
            client_id = settings.gsc_client_id
            client_secret = settings.gsc_client_secret
            refresh_token = settings.gsc_refresh_token

        if not refresh_token:
            raise IntegrationError(
                "GSC OAuth credentials not configured. "
                "Run scripts/gsc_auth.py to generate token, "
                "then set GSC_CLIENT_ID, GSC_CLIENT_SECRET, GSC_REFRESH_TOKEN in .env.",
                status_code=None,
                integration_name=self.name,
            )

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=_SCOPES,
        )

        if not creds.valid:
            creds.refresh(Request())

        return creds

    def _build_service(self, org_settings: dict | None = None):
        from googleapiclient.discovery import build

        creds = self._get_credentials(org_settings)
        return build("searchconsole", "v1", credentials=creds)

    # ── Public methods ────────────────────────────────────────────────────────

    async def list_sites(
        self,
        org_id: str | None = None,
        db: Any | None = None,
    ) -> list[str]:
        """Return verified site URLs."""
        org_settings = None
        if org_id and db:
            org_settings = await self._get_org_settings(org_id, db)

        service = self._build_service(org_settings)
        result = service.sites().list().execute()
        return [s["siteUrl"] for s in result.get("siteEntry", [])]

    async def get_search_analytics(
        self,
        site_url: str,
        start_date: date | str,
        end_date: date | str,
        dimensions: list[str] | None = None,
        row_limit: int = 1000,
        org_id: str | None = None,
        db: Any | None = None,
    ) -> list[dict]:
        """Return search analytics rows normalised to {query, clicks, impressions, ctr, position}."""
        if dimensions is None:
            dimensions = ["query"]

        if os.getenv("USE_MOCK_DATA") == "true":
            _mock_rows = [
                {"keys": ["ai marketing automation"], "clicks": 142,
                 "impressions": 1500, "ctr": 0.094, "position": 4.2},
                {"keys": ["multi agent system tutorial"], "clicks": 12,
                 "impressions": 850, "ctr": 0.014, "position": 14.5},
                {"keys": ["project management software"], "clicks": 8,
                 "impressions": 600, "ctr": 0.013, "position": 22.1},
            ]
            return [_normalise_row(r, dimensions) for r in _mock_rows]

        org_settings = None
        if org_id and db:
            org_settings = await self._get_org_settings(org_id, db)

        service = self._build_service(org_settings)
        request_body = {
            "startDate": str(start_date),
            "endDate": str(end_date),
            "dimensions": dimensions,
            "rowLimit": row_limit,
        }
        response = (
            service.searchanalytics()
            .query(siteUrl=site_url, body=request_body)
            .execute()
        )
        rows = response.get("rows", [])
        return [_normalise_row(row, dimensions) for row in rows]

    async def get_sitemaps(
        self,
        site_url: str,
        org_id: str | None = None,
        db: Any | None = None,
    ) -> list[str]:
        org_settings = None
        if org_id and db:
            org_settings = await self._get_org_settings(org_id, db)

        service = self._build_service(org_settings)
        from urllib.parse import quote
        result = service.sitemaps().list(siteUrl=site_url).execute()
        return [sm["path"] for sm in result.get("sitemap", [])]

    async def health_check(self) -> bool:
        """Check Google API reachability — no credentials required."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get("https://oauth2.googleapis.com/token")
            return resp.status_code < 500
        except Exception:
            return False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalise_row(row: dict, dimensions: list[str]) -> dict:
    """Flatten GSC's {keys: [...], clicks, impressions, ctr, position} into a flat dict."""
    keys = row.get("keys", [])
    out: dict[str, Any] = {}
    for i, dim in enumerate(dimensions):
        out[dim] = keys[i] if i < len(keys) else None
    out["clicks"] = int(row.get("clicks", 0))
    out["impressions"] = int(row.get("impressions", 0))
    out["ctr"] = round(float(row.get("ctr", 0.0)), 4)
    out["position"] = round(float(row.get("position", 0.0)), 1)
    return out
