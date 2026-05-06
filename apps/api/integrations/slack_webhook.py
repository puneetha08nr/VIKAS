"""SlackWebhookIntegration — posts messages to a Slack incoming webhook.

Extends BaseIntegration for circuit-breaker and rate-limiting.
send_message() NEVER raises — returns False silently when the webhook
URL is unconfigured or when the request fails.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from integrations.base import BaseIntegration

logger = logging.getLogger(__name__)


class SlackWebhookIntegration(BaseIntegration):
    name = "slack_webhook"
    base_url = "https://hooks.slack.com"
    max_requests_per_minute = 30

    def __init__(self, webhook_url: str = "") -> None:
        super().__init__()
        self._webhook_url = webhook_url

    async def health_check(self) -> bool:
        return bool(self._webhook_url) and not self._circuit.is_open()

    async def get_credentials(self, org_id: str, db: AsyncSession) -> dict[str, Any]:
        return {}

    async def send_message(self, text: str) -> bool:
        """POST text to the Slack incoming webhook.

        Returns True on success, False on any failure (unconfigured, network
        error, non-2xx). Never raises.
        """
        if not self._webhook_url:
            logger.warning(
                "slack_webhook: SLACK_WEBHOOK_URL not configured — skipping notification"
            )
            return False

        if self._circuit.is_open():
            logger.warning("slack_webhook: circuit open, skipping notification")
            return False

        if not self._bucket.consume():
            logger.warning("slack_webhook: rate limit hit, skipping notification")
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self._webhook_url,
                    json={"text": text},
                )
            if response.status_code == 200:
                self._circuit.record_success()
                return True
            logger.warning(
                "slack_webhook: unexpected status %d: %s",
                response.status_code,
                response.text[:200],
            )
            self._circuit.record_failure()
            return False
        except Exception as exc:
            logger.warning("slack_webhook: request failed: %s", exc)
            self._circuit.record_failure()
            return False
