from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.agent_base import BaseAgent

REGISTRY: dict[str, type["BaseAgent"]] = {}


def register(cls: type["BaseAgent"]) -> type["BaseAgent"]:
    """Class decorator — adds the agent to the global registry."""
    REGISTRY[cls.name] = cls
    return cls


def get(name: str) -> "BaseAgent":
    """Return a fresh instance of the named agent."""
    if name not in REGISTRY:
        raise KeyError(f"Agent '{name}' not found in registry. Registered: {list(REGISTRY)}")
    return REGISTRY[name]()


def list_agents() -> list[str]:
    return list(REGISTRY.keys())


def import_all_agents() -> None:
    """Import all agent modules so @register decorators fire."""
    import importlib
    import logging

    agent_modules = [
        "agents.seo.keyword_research",
        "agents.seo.keyword_validator",
        "agents.seo.opportunity_scorer",
        "agents.seo.gap_analyzer",
        "agents.seo.rank_tracker",
        "agents.content.content_director",
        "agents.content.article_planner",
        "agents.content.article_writer",
        "agents.content.linkedin_agent",
        "agents.knowledge.document_ingester",
        "agents.knowledge.brand_voice_keeper",
        "agents.knowledge.rag_searcher",
        "agents.knowledge.wordpress_publisher",
    ]

    for module in agent_modules:
        try:
            importlib.import_module(module)
        except ImportError as exc:
            logging.warning("Could not import agent module %s: %s", module, exc)
