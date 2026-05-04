"""DataForSEO integration — keyword volume, KD, CPC enrichment, and keyword ideas.

Credentials live in org settings (dataforseo_login / dataforseo_password)
or fall back to DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD env vars.

On missing credentials or any HTTP error, raises IntegrationError.
The keyword_validator agent catches IntegrationError and falls back to
existing DB values with data_source = 'llm_estimate'.
"""
from __future__ import annotations

import os
from typing import Any

import httpx as _httpx
from sqlalchemy.ext.asyncio import AsyncSession

from integrations.base import BaseIntegration, IntegrationError

# ── Module-level helpers ──────────────────────────────────────────────────────

async def _get_google_suggestions(seed: str) -> list[str]:
    """Fetch keyword suggestions from Google Suggest. Free, no auth.

    Runs all queries concurrently to minimise event-loop pressure when called
    inside an active asyncpg session.
    """
    import asyncio
    base_url = "https://suggestqueries.google.com/complete/search"
    queries = [seed] + [f"{seed} {c}" for c in "abcdefghijklmnoprstw"]

    async def _fetch(client: _httpx.AsyncClient, query: str) -> list[str]:
        try:
            r = await client.get(base_url, params={"q": query, "client": "firefox", "hl": "en"})
            r.raise_for_status()
            data = r.json()
            return [s.strip() for s in (data[1] if len(data) > 1 else [])
                    if s.strip() and s.strip() != seed]
        except Exception:
            return []

    async with _httpx.AsyncClient(timeout=10) as client:
        batches = await asyncio.gather(*[_fetch(client, q) for q in queries[:8]])

    results: set[str] = set()
    for batch in batches:
        results.update(batch)
    return list(results)


def _estimate_kd(competition_index: float) -> float:
    """Convert DataForSEO competition_index (0-100) to KD (0-10)."""
    return round(float(competition_index or 0) / 10, 1)


def _infer_intent(keyword: str) -> str:
    """Rule-based intent from keyword text. No LLM."""
    kw = keyword.lower()
    if any(w in kw for w in [
        "buy", "price", "cost", "pricing", "cheap",
        "discount", "order", "purchase", "subscription",
        "plan", "trial", "free",
    ]):
        return "transactional"
    if any(w in kw for w in [
        "login", "sign in", "signup", "download",
        "install", "app", "official", "support",
    ]):
        return "navigational"
    if any(w in kw for w in [
        "best", "top", "review", "compare", "vs",
        "alternative", "tool", "software", "platform",
        "solution", "service", "guide",
    ]):
        return "commercial"
    return "informational"


# ── Integration class ─────────────────────────────────────────────────────────

class DataForSEOIntegration(BaseIntegration):
    name = "dataforseo"
    base_url = "https://api.dataforseo.com"
    max_requests_per_minute = 60

    async def health_check(self) -> bool:
        try:
            await self.request("GET", "/v3/appendix/user_data")
            return True
        except Exception:
            return False

    async def get_credentials(self, org_id: str, db: AsyncSession) -> dict[str, str]:
        settings = await self._get_org_settings(org_id, db)
        login = settings.get("dataforseo_login") or os.getenv("DATAFORSEO_LOGIN", "")
        password = settings.get("dataforseo_password") or os.getenv("DATAFORSEO_PASSWORD", "")
        if not login or not password:
            raise IntegrationError(
                "DataForSEO credentials not configured — set DATAFORSEO_LOGIN/PASSWORD",
                status_code=None,
                integration_name=self.name,
            )
        return {"login": login, "password": password}

    async def get_keyword_metrics(
        self,
        keywords: list[str],
        org_id: str,
        db: AsyncSession,
    ) -> dict[str, dict[str, Any]]:
        """Return {keyword_text: {volume, kd, cpc}} for every keyword.

        Raises IntegrationError if credentials are missing or the request fails.
        Unknown keywords are omitted; the caller falls back to existing DB values.
        """
        creds = await self.get_credentials(org_id, db)

        payload = [{"keywords": keywords, "location_code": 2840, "language_code": "en"}]
        response = await self.request(
            "POST",
            "/v3/keywords_data/google_ads/search_volume/live",
            json=payload,
            auth=(creds["login"], creds["password"]),
        )

        result: dict[str, dict[str, Any]] = {}
        for task in response.get("tasks") or []:
            for item in task.get("result") or []:
                kw = str(item.get("keyword") or "").strip()
                if not kw:
                    continue
                result[kw] = {
                    "volume": item.get("search_volume"),
                    "kd": item.get("keyword_difficulty"),
                    "cpc": item.get("cpc"),
                }
        return result

    async def get_keyword_ideas(
        self,
        seed: str,
        org_id: str,
        db: AsyncSession,
        location_code: int = 2840,
        language_code: str = "en",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Two-step keyword ideas: Google Suggest → DataForSEO metrics.

        Step 1: Google Suggest generates keyword ideas (free, no auth).
        Step 2: keywords_data/google_ads/search_volume/live fetches real metrics.

        Returns list of {keyword, volume, kd, cpc, intent}.
        Raises IntegrationError if credentials are missing or either step fails.
        """
        creds = await self.get_credentials(org_id, db)

        # Step 1: Google Suggest — free, no auth
        keyword_ideas = await _get_google_suggestions(seed)
        if not keyword_ideas:
            raise IntegrationError(
                "Google Suggest returned no ideas for this seed",
                status_code=None,
                integration_name=self.name,
            )

        keyword_ideas = keyword_ideas[:limit]

        # Step 2: DataForSEO — real metrics
        payload = [{
            "keywords": keyword_ideas,
            "location_code": location_code,
            "language_code": language_code,
        }]

        result = await self.request(
            "POST",
            "/v3/keywords_data/google_ads/search_volume/live",
            json=payload,
            auth=(creds["login"], creds["password"]),
        )

        tasks = result.get("tasks") or []
        if not tasks:
            raise IntegrationError(
                "DataForSEO returned empty response",
                status_code=None,
                integration_name=self.name,
            )

        task = tasks[0]
        if task.get("status_code") != 20000:
            raise IntegrationError(
                f"DataForSEO error: {task.get('status_message')}",
                status_code=task.get("status_code"),
                integration_name=self.name,
            )

        items = task.get("result") or []

        return [
            {
                "keyword": item["keyword"],
                "volume": int(item.get("search_volume") or 0),
                "kd": _estimate_kd(item.get("competition_index") or 0),
                "cpc": float(item.get("cpc") or 0.0),
                "intent": _infer_intent(item["keyword"]),
            }
            for item in items
            if item.get("keyword")
        ]
