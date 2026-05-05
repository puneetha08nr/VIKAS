"""EmailIntegration — sends HTML emails via SMTP/STARTTLS.

Extends BaseIntegration for circuit-breaker and rate-limiting.
send_email() NEVER raises — returns False silently when SMTP settings
are incomplete or when the send fails.

smtplib is synchronous; the blocking call is offloaded to a thread
via run_in_executor so the event loop stays responsive.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from integrations.base import BaseIntegration

logger = logging.getLogger(__name__)


class EmailIntegration(BaseIntegration):
    name = "email"
    base_url = ""  # not HTTP-based; base_url unused
    max_requests_per_minute = 60

    def __init__(
        self,
        smtp_host: str = "",
        smtp_port: int = 587,
        smtp_user: str = "",
        smtp_password: str = "",
    ) -> None:
        super().__init__()
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._smtp_user = smtp_user
        self._smtp_password = smtp_password

    async def health_check(self) -> bool:
        return bool(self._smtp_host and self._smtp_user and self._smtp_password)

    async def get_credentials(self, org_id: str, db: AsyncSession) -> dict[str, Any]:
        return {}

    async def send_email(self, to: str, subject: str, body_html: str) -> bool:
        """Send an HTML email via SMTP STARTTLS.

        Returns True on success, False on any failure (unconfigured, auth error,
        network error). Never raises.
        """
        if not all([self._smtp_host, self._smtp_user, self._smtp_password, to]):
            logger.warning("email: SMTP settings incomplete — skipping notification")
            return False

        if self._circuit.is_open():
            logger.warning("email: circuit open, skipping notification")
            return False

        if not self._bucket.consume():
            logger.warning("email: rate limit hit, skipping notification")
            return False

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                self._send_sync,
                to,
                subject,
                body_html,
            )
            self._circuit.record_success()
            return True
        except Exception as exc:
            logger.warning("email: send failed: %s", exc)
            self._circuit.record_failure()
            return False

    def _send_sync(self, to: str, subject: str, body_html: str) -> None:
        """Blocking SMTP send — called via run_in_executor."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._smtp_user
        msg["To"] = to
        msg.attach(MIMEText(body_html, "html"))

        ctx = ssl.create_default_context()
        with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.login(self._smtp_user, self._smtp_password)
            server.sendmail(self._smtp_user, [to], msg.as_string())
