import asyncio
import uuid
from datetime import datetime, timezone

from celery import Celery
from pydantic import BaseModel, Field

from config.settings import settings

celery_app = Celery("vikas", broker=settings.redis_url)
celery_app.conf.task_serializer = "json"
celery_app.conf.accept_content = ["json"]


class AgentCommand(BaseModel):
    agent_name: str
    org_id: str
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    params: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def dispatch(command: AgentCommand) -> str:
    """Serialize the command and send it to the Celery queue. Returns run_id."""
    celery_app.send_task(
        "core.task_queue.execute_agent",
        args=[command.model_dump(mode="json")],
    )
    return command.run_id


@celery_app.task(name="core.task_queue.execute_agent")
def execute_agent(command_dict: dict) -> None:
    """Celery entry point — deserializes the command and runs the agent."""
    asyncio.run(_run_agent(command_dict))


async def _run_agent(command_dict: dict) -> None:
    from pathlib import Path

    from core.agent_base import AgentContext
    from core.agent_registry import get as get_agent
    from core.cost_tracker import CostTracker
    from core.llm_router import LLMRouter
    from db.session import org_session

    command = AgentCommand(**command_dict)
    agent = get_agent(command.agent_name)

    config_path = Path(__file__).parent.parent / "config" / "model_tiers.yaml"
    router = LLMRouter(config_path, CostTracker(), settings)

    async with org_session(command.org_id) as db:
        ctx = AgentContext(
            org_id=command.org_id,
            run_id=command.run_id,
            params=command.params,
            config={},
            db=db,
            llm=router,
        )
        await agent.run(ctx)
