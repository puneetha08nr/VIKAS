"""Google Search Console integration.

Uses the Search Analytics API v3 via service account credentials stored
in the org's settings JSON blob under the key ``gsc_service_account_json``.
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
_GSC_BASE = "https://www.googleapis.com/webmasters/v3"


class GoogleSearchConsoleIntegration(BaseIntegration):
    name = "google_search_console"
    base_url = _GSC_BASE
    max_requests_per_minute = 200  # GSC quota is generous

    # ── Auth ──────────────────────────────────────────────────────────────────

    async def get_credentials(self, org_id: str, db: AsyncSession) -> dict:
        settings = await self._get_org_settings(org_id, db)
        raw = settings.get("gsc_service_account_json")
        if not raw:
            raise IntegrationError(
                "gsc_service_account_json not configured for this org",
                status_code=None,
                integration_name=self.name,
            )
        return json.loads(raw) if isinstance(raw, str) else raw

    def _build_authed_client(self, service_account_info: dict) -> httpx.AsyncClient:
        creds = google.oauth2.service_account.Credentials.from_service_account_info(
            service_account_info, scopes=_SCOPES
        )
        # Refresh synchronously once to get the token
        creds.refresh(google.auth.transport.requests.Request())
        return httpx.AsyncClient(
            headers={"Authorization": f"Bearer {creds.token}"},
            base_url=_GSC_BASE,
        )

    # ── Public methods ────────────────────────────────────────────────────────

    async def get_search_analytics(
        self,
        site_url: str,
        start_date: date | str,
        end_date: date | str,
        dimensions: list[str],
        org_id: str,
        db: AsyncSession,
        row_limit: int = 1000,
    ) -> list[dict]:
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

        data = resp.json()
        return data.get("rows", [])

    async def get_sitemaps(self, site_url: str, org_id: str, db: AsyncSession) -> list[str]:
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

        data = resp.json()
        return [sm["path"] for sm in data.get("sitemap", [])]

    async def list_sites(self, org_id: str, db: AsyncSession) -> list[str]:
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

        data = resp.json()
        return [entry["siteUrl"] for entry in data.get("siteEntry", [])]

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://www.googleapis.com/discovery/v1/apis/webmasters/v3/rest",
                    timeout=5,
                )
            return resp.status_code == 200
        except Exception:
            return False


def _encode_site(site_url: str) -> str:
    """URL-encode the site identifier for use in GSC API paths."""
    from urllib.parse import quote
    return quote(site_url, safe="")
