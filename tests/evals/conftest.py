"""Shared pytest fixtures for all eval tests."""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure tests/evals/ is importable (for `from base import ...` in eval files)
sys.path.insert(0, str(Path(__file__).parent))

# ── Default mock LLM response: 3 keyword objects with all fields ───────────────
_KEYWORD_RESEARCH_MOCK_RESPONSE = (
    '[{"keyword": "ai marketing tools", "volume": 8100, "kd": 42.0, "cpc": 4.50,'
    ' "intent": "commercial", "reason": "high value"},'
    ' {"keyword": "ai content marketing strategy", "volume": 3200, "kd": 38.5, "cpc": 5.10,'
    ' "intent": "informational", "reason": "informational intent"},'
    ' {"keyword": "marketing automation with ai", "volume": 5400, "kd": 35.0, "cpc": 6.20,'
    ' "intent": "commercial", "reason": "commercial"}]'
)


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=_KEYWORD_RESEARCH_MOCK_RESPONSE)
    llm.last_tokens_used = 150
    llm.last_cost_usd = 0.0003
    return llm


@pytest.fixture
def structural_ctx(mock_db: AsyncMock, mock_llm: MagicMock):
    """AgentContext wired with mocks, ready for structural checks."""
    from core.agent_base import AgentContext
    return AgentContext(
        org_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000099",
        params={},           # each test overrides via ctx.params
        config={},
        db=mock_db,
        llm=mock_llm,
    )
