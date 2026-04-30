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
