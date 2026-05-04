import logging
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, SkipValidation
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.llm_router import LLMRouter

logger = logging.getLogger(__name__)


class AgentContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    org_id: str
    run_id: str
    params: dict[str, Any]
    config: dict[str, Any]
    db: SkipValidation[AsyncSession]
    llm: SkipValidation[LLMRouter]


class AgentResult(BaseModel):
    status: str  # success | failed | partial
    data: dict[str, Any] = {}
    tokens_used: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0
    error: str | None = None


class PreflightResult(BaseModel):
    ok: bool
    reason: str | None = None


class BaseAgent(ABC):
    name: str
    tier: str
    version: str = "1.0.0"

    async def run(self, ctx: AgentContext) -> AgentResult:
        """Orchestrates the full agent lifecycle. Do not override."""
        start = time.monotonic()
        await self._create_run_record(ctx)

        preflight = self.preflight(ctx)
        if not preflight.ok:
            result = AgentResult(
                status="failed",
                error=f"Preflight failed: {preflight.reason}",
                duration_ms=int((time.monotonic() - start) * 1000),
            )
            await self._audit(ctx, result)
            self._notify(ctx, result)
            return result

        try:
            result = await self.execute(ctx)
        except Exception as exc:
            logger.exception("Agent %s raised during execute | run_id=%s", self.name, ctx.run_id)
            result = AgentResult(status="failed", error=str(exc))

        result.duration_ms = int((time.monotonic() - start) * 1000)
        await self._audit(ctx, result)
        self._notify(ctx, result)
        return result

    def preflight(self, ctx: AgentContext) -> PreflightResult:
        """Base checks. Subclasses can extend by calling super() and adding their own checks."""
        return PreflightResult(ok=True)

    @abstractmethod
    async def execute(self, ctx: AgentContext) -> AgentResult:
        """Implement agent logic here. Only method subclasses need to write."""
        ...

    async def call_llm(self, ctx: AgentContext, prompt: str, **kwargs: Any) -> str:
        """Route to the correct model tier, track tokens and cost."""
        return await ctx.llm.complete(
            prompt=prompt,
            tier=self.tier,
            org_id=ctx.org_id,
            run_id=ctx.run_id,
            db=ctx.db,
            **kwargs,
        )

    async def _create_run_record(self, ctx: AgentContext) -> None:
        # ON CONFLICT DO NOTHING: the API endpoint may have already created this row.
        await ctx.db.execute(
            text(
                "INSERT INTO agent_runs "
                "(id, org_id, agent_name, status, tokens_in, tokens_out, cost_usd, started_at) "
                "VALUES (:id, :org_id, :agent_name, 'running', 0, 0, 0, now()) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"id": ctx.run_id, "org_id": ctx.org_id, "agent_name": self.name},
        )
        await ctx.db.flush()

    async def _audit(self, ctx: AgentContext, result: AgentResult) -> None:
        """Write final status, duration, and error to agent_runs."""
        await ctx.db.execute(
            text(
                "UPDATE agent_runs SET "
                "status = :status, duration_ms = :duration_ms, "
                "cost_usd = cost_usd + :cost_usd, "
                "error = :error, completed_at = :completed_at "
                "WHERE id = :id"
            ),
            {
                "id": ctx.run_id,
                "status": result.status,
                "duration_ms": result.duration_ms,
                "cost_usd": result.cost_usd,
                "error": result.error,
                "completed_at": datetime.now(UTC),
            },
        )
        await ctx.db.commit()

    def _notify(self, ctx: AgentContext, result: AgentResult) -> None:
        """Log failures. Slack/email hook placeholder."""
        if result.status == "failed":
            logger.warning(
                "Agent failed | agent=%s run_id=%s error=%s",
                self.name,
                ctx.run_id,
                result.error,
            )
