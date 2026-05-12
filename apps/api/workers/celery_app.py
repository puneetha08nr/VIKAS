import asyncio
import uuid

from celery import Celery
from celery.schedules import crontab

from config.settings import settings

celery_app = Celery(
    "vikas",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["core.task_queue"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Ack only after the task completes — prevents silent loss on worker crash.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Keep results for 24 h then expire.
    result_expires=86400,
    beat_schedule={
        # Sentiment pipeline: filter → analysis → aggregation, daily at 03:00 UTC.
        # Runs after midnight collection windows have closed.
        "nightly-sentiment-pipeline": {
            "task": "workers.celery_app.run_sentiment_pipeline_all_orgs",
            "schedule": crontab(hour=3, minute=0),
        },
        # Source credibility scoring: one-time per new source, daily at 04:00 UTC.
        "nightly-source-credibility": {
            "task": "workers.celery_app.run_source_credibility_all_orgs",
            "schedule": crontab(hour=4, minute=0),
        },
    },
)


# ── Nightly sweep tasks ───────────────────────────────────────────────────────
# These tasks fetch active org IDs from the DB and dispatch per-org agent runs.
# They are triggered by the beat scheduler, not by the API.

@celery_app.task(name="workers.celery_app.run_sentiment_pipeline_all_orgs")
def run_sentiment_pipeline_all_orgs() -> None:
    """Dispatch sentiment_orchestrator for every active org."""
    asyncio.run(_dispatch_for_all_orgs("sentiment_orchestrator", {}))


@celery_app.task(name="workers.celery_app.run_source_credibility_all_orgs")
def run_source_credibility_all_orgs() -> None:
    """Dispatch sentiment_source_credibility_scorer for every active org."""
    asyncio.run(_dispatch_for_all_orgs("sentiment_source_credibility_scorer", {}))


async def _dispatch_for_all_orgs(agent_name: str, params: dict) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from core.task_queue import AgentCommand, dispatch

    engine = create_async_engine(settings.admin_database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await session.execute(
                text("SELECT id FROM organizations ORDER BY created_at")
            )
            org_ids = [str(row[0]) for row in result.fetchall()]
    finally:
        await engine.dispose()

    for org_id in org_ids:
        cmd = AgentCommand(
            agent_name=agent_name,
            org_id=org_id,
            run_id=str(uuid.uuid4()),
            params=params,
        )
        dispatch(cmd)
