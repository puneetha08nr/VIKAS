import asyncio
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from config.settings import settings
from core.agent_registry import import_all_agents
from workers.celery_app import celery_app

import_all_agents()


class AgentCommand(BaseModel):
    agent_name: str
    org_id: str
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    params: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def dispatch(command: AgentCommand) -> str:
    """Serialize the command and send it to the Celery queue. Returns run_id."""
    celery_app.send_task(
        "core.task_queue.execute_agent",
        args=[command.model_dump(mode="json")],
    )
    return command.run_id


@celery_app.task(name="core.task_queue.execute_agent")
def execute_agent(command_dict: dict) -> None:
    """Celery entry point — always runs on a fresh event loop to avoid pool conflicts."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_agent(command_dict))
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
        asyncio.set_event_loop(None)


async def _run_agent(command_dict: dict) -> None:
    from pathlib import Path

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from core.agent_base import AgentContext
    from core.agent_registry import get as get_agent
    from core.cost_tracker import CostTracker
    from core.llm_router import LLMRouter

    command = AgentCommand(**command_dict)
    agent = get_agent(command.agent_name)

    config_path = Path(__file__).parent.parent / "config" / "model_tiers.yaml"
    router = LLMRouter(config_path, CostTracker(), settings)

    # Fresh engine per task — never reuse the FastAPI engine across event loops.
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as session:
            await session.execute(
                text(f"SET app.current_org_id = '{command.org_id}'")
            )
            ctx = AgentContext(
                org_id=command.org_id,
                run_id=command.run_id,
                params=command.params,
                config={},
                db=session,
                llm=router,
            )
            await agent.run(ctx)
    finally:
        await engine.dispose()
