"""
Shared types, LLM-as-judge, and DB logging for the Vikas eval framework.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ── Result dataclasses ─────────────────────────────────────────────────────────

@dataclass
class StructuralCheck:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class StructuralResult:
    agent_name: str
    passed: bool
    checks: list[StructuralCheck] = field(default_factory=list)
    run_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_log_row(self) -> dict[str, Any]:
        return {
            "id": str(uuid.uuid4()),
            "org_id": None,
            "agent_name": self.agent_name,
            "eval_type": "structural",
            "score": 1.0 if self.passed else 0.0,
            "threshold": 1.0,
            "passed": self.passed,
            "inputs": None,
            "outputs": json.dumps({
                "checks": [
                    {"name": c.name, "passed": c.passed, "detail": c.detail}
                    for c in self.checks
                ]
            }),
            "notes": None,
        }


@dataclass
class RelevanceResult:
    agent_name: str
    score: float
    threshold: float
    passed: bool
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    reasoning: str = ""
    run_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_log_row(self) -> dict[str, Any]:
        return {
            "id": str(uuid.uuid4()),
            "org_id": None,
            "agent_name": self.agent_name,
            "eval_type": "relevance",
            "score": self.score,
            "threshold": self.threshold,
            "passed": self.passed,
            "inputs": json.dumps(self.inputs),
            "outputs": json.dumps(self.outputs),
            "notes": self.reasoning,
        }


@dataclass
class GroundTruthSample:
    """One labelled example for monthly human spot-checks."""
    description: str
    input_params: dict[str, Any]
    expected_fields: dict[str, Any]   # reference checklist for the human reviewer
    notes: str = ""                   # additional guidance shown to reviewer


@dataclass
class GroundTruthResult:
    agent_name: str
    sample_index: int
    description: str
    input_params: dict[str, Any]
    actual_outputs: dict[str, Any]
    human_score: int                  # 1-5
    notes: str = ""

    def to_log_row(self) -> dict[str, Any]:
        return {
            "id": str(uuid.uuid4()),
            "org_id": None,
            "agent_name": self.agent_name,
            "eval_type": "ground_truth",
            "score": self.human_score / 5.0,
            "threshold": 0.6,         # 3/5 is the minimum acceptable score
            "passed": self.human_score >= 3,
            "inputs": json.dumps(self.input_params),
            "outputs": json.dumps(self.actual_outputs),
            "notes": f"[sample {self.sample_index}: {self.description}] {self.notes}".strip(),
        }


# ── LLM-as-judge ──────────────────────────────────────────────────────────────

async def judge_relevance(
    agent_name: str,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    criteria: str,
) -> tuple[float, str]:
    """Call LLM judge to score agent output quality. Returns (score 0–1, reasoning)."""
    prompt = (
        f"You are an impartial quality evaluator for an AI marketing agent.\n"
        f"Agent: {agent_name}\n\n"
        f"Input passed to agent:\n{json.dumps(inputs, indent=2)}\n\n"
        f"Agent output:\n{json.dumps(outputs, indent=2)}\n\n"
        f"Evaluation criteria:\n{criteria}\n\n"
        f"Score 0.0 (terrible) to 1.0 (excellent).\n"
        f"Return ONLY valid JSON, no markdown: "
        f'{{ "score": <float>, "reasoning": "<one sentence>" }}'
    )
    try:
        import litellm  # already a project dependency
        response = await litellm.acompletion(
            model="claude-haiku-4-5-20251001",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.0,
        )
        raw = (response.choices[0].message.content or "").strip()
        parsed = json.loads(raw)
        score = max(0.0, min(1.0, float(parsed["score"])))
        reasoning = str(parsed.get("reasoning", ""))
        return score, reasoning
    except Exception as exc:
        logger.warning("Relevance judge call failed: %s", exc)
        return 0.5, f"Judge unavailable: {exc}"


# ── DB logging helper ──────────────────────────────────────────────────────────

async def log_eval_result(db: Any, row: dict[str, Any]) -> None:
    """Insert one row into evals_log. Accepts AsyncSession or None (no-op)."""
    if db is None:
        return
    from sqlalchemy import text as _text
    await db.execute(
        _text(
            "INSERT INTO evals_log "
            "(id, org_id, agent_name, eval_type, score, threshold, passed, inputs, outputs, notes) "
            "VALUES (:id, :org_id, :agent_name, :eval_type, :score, :threshold, "
            ":passed, :inputs::jsonb, :outputs::jsonb, :notes)"
        ),
        row,
    )
    await db.commit()
