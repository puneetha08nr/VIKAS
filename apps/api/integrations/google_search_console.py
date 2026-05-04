"""Google Search Console integration.

Uses the Search Analytics API v3 via service account credentials.

Credential resolution order (first wins):
  1. org settings JSON blob — production path (org_id + db provided)
  2. GSC_SERVICE_ACCOUNT_JSON env var — dev / CLI / health-check path
"""
import json
import logging
from datetime import date
from typing import Any

import google.auth.transport.requests
import google.oauth2.service_account
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from integrations.base import BaseIntegration, IntegrationError

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
_GSC_BASE = "https://searchconsole.googleapis.com/webmasters/v3"


class GoogleSearchConsoleIntegration(BaseIntegration):
    name = "google_search_console"
    base_url = _GSC_BASE
    max_requests_per_minute = 200

    # ── Auth ──────────────────────────────────────────────────────────────────

    async def get_credentials(
        self,
        org_id: str | None = None,
        db: AsyncSession | None = None,
    ) -> dict:
        """Return parsed service-account JSON dict.

        Falls back to GSC_SERVICE_ACCOUNT_JSON env var when org_id/db are
        not provided (CLI, health-check, dev testing).
        """
        if org_id and db:
            settings = await self._get_org_settings(org_id, db)
            raw = settings.get("gsc_service_account_json")
            if raw:
                return json.loads(raw) if isinstance(raw, str) else raw

        # Env-var fallback
        from config.settings import settings as app_settings
        raw = app_settings.gsc_service_account_json
        if not raw:
            raise IntegrationError(
                "GSC credentials not configured — set gsc_service_account_json "
                "in org settings or GSC_SERVICE_ACCOUNT_JSON env var",
                status_code=None,
                integration_name=self.name,
            )
        return json.loads(raw) if isinstance(raw, str) else raw

    def _build_authed_client(self, service_account_info: dict) -> httpx.AsyncClient:
        creds = google.oauth2.service_account.Credentials.from_service_account_info(
            service_account_info, scopes=_SCOPES
        )
        creds.refresh(google.auth.transport.requests.Request())
        return httpx.AsyncClient(
            headers={"Authorization": f"Bearer {creds.token}"},
            base_url=_GSC_BASE,
            timeout=30.0,
        )

    # ── Public methods ────────────────────────────────────────────────────────

    async def get_search_analytics(
        self,
        site_url: str,
        start_date: date | str,
        end_date: date | str,
        dimensions: list[str] | None = None,
        row_limit: int = 1000,
        org_id: str | None = None,
        db: AsyncSession | None = None,
    ) -> list[dict]:
        """Return search analytics rows normalised to {query, clicks, impressions, ctr, position}."""
        if dimensions is None:
            dimensions = ["query"]

        creds_info = await self.get_credentials(org_id, db)
        async with self._build_authed_client(creds_info) as client:
            payload: dict[str, Any] = {
                "startDate": str(start_date),
                "endDate": str(end_date),
                "dimensions": dimensions,
                "rowLimit": row_limit,
            }
            try:
                resp = await client.post(
                    f"/sites/{_encode_site(site_url)}/searchAnalytics/query",
                    json=payload,
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise IntegrationError(
                    f"GSC search analytics failed: {exc}",
                    status_code=exc.response.status_code,
                    integration_name=self.name,
                ) from exc

        rows = resp.json().get("rows", [])
        return [_normalise_row(row, dimensions) for row in rows]

    async def get_sitemaps(
        self,
        site_url: str,
        org_id: str | None = None,
        db: AsyncSession | None = None,
    ) -> list[str]:
        creds_info = await self.get_credentials(org_id, db)
        async with self._build_authed_client(creds_info) as client:
            try:
                resp = await client.get(f"/sites/{_encode_site(site_url)}/sitemaps")
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise IntegrationError(
                    f"GSC sitemaps failed: {exc}",
                    status_code=exc.response.status_code,
                    integration_name=self.name,
                ) from exc

        return [sm["path"] for sm in resp.json().get("sitemap", [])]

    async def list_sites(
        self,
        org_id: str | None = None,
        db: AsyncSession | None = None,
    ) -> list[str]:
        """Return verified site URLs. Callable without org_id/db for dev testing."""
        creds_info = await self.get_credentials(org_id, db)
        async with self._build_authed_client(creds_info) as client:
            try:
                resp = await client.get("/sites")
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise IntegrationError(
                    f"GSC list sites failed: {exc}",
                    status_code=exc.response.status_code,
                    integration_name=self.name,
                ) from exc

        return [entry["siteUrl"] for entry in resp.json().get("siteEntry", [])]

    async def health_check(self) -> bool:
        """Check Google API reachability — no credentials required.

        Pings the OAuth2 token endpoint (always returns 405 on GET, never 5xx)
        to confirm network connectivity to Google's APIs.
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get("https://oauth2.googleapis.com/token")
            # 405 Method Not Allowed is expected for GET — still means we can reach Google
            return resp.status_code < 500
        except Exception:
            return False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _encode_site(site_url: str) -> str:
    from urllib.parse import quote
    return quote(site_url, safe="")


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
