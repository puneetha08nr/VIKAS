from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class CostTracker:
    async def add(
        self,
        org_id: str,
        run_id: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
        db: AsyncSession,
    ) -> None:
        """Increment token counts and cost on the in-flight agent_run row."""
        await db.execute(
            text(
                "UPDATE agent_runs SET "
                "tokens_in  = tokens_in  + :tokens_in, "
                "tokens_out = tokens_out + :tokens_out, "
                "cost_usd   = cost_usd   + :cost_usd, "
                "model_used = :model "
                "WHERE id = :run_id"
            ),
            {
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": cost_usd,
                "model": model,
                "run_id": run_id,
            },
        )
        await db.flush()

    async def get_daily_total(self, org_id: str, db: AsyncSession) -> float:
        """Sum cost_usd for this org since midnight UTC today."""
        result = await db.execute(
            text(
                "SELECT COALESCE(SUM(cost_usd), 0.0) "
                "FROM agent_runs "
                "WHERE org_id = :org_id "
                "AND started_at >= CURRENT_DATE"
            ),
            {"org_id": org_id},
        )
        return float(result.scalar())

    async def check_limit(
        self, org_id: str, daily_limit_usd: float, db: AsyncSession
    ) -> bool:
        """Return True if the org is still under its daily spend limit."""
        total = await self.get_daily_total(org_id, db)
        return total < daily_limit_usd
