"""Integration tests for the keyword research pipeline.

test_keyword_research_end_to_end  — happy path: agent writes keywords, logs cost
test_rls_isolation                — cross-org data must NEVER be visible (security gate)
"""
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from _helpers import org_session_for_test

_GOLDEN = json.loads(
    (Path(__file__).parents[2] / "tests" / "golden_traces" / "keyword_research_trace.json")
    .read_text()
)


# ── Test 1: Happy path ────────────────────────────────────────────────────────

async def test_keyword_research_end_to_end(test_org, db_engine):
    """Run KeywordResearchAgent in-process; verify keywords and audit row in DB."""
    import agents.seo.keyword_research  # noqa: F401 — ensures @register runs

    from core.agent_base import AgentContext
    from core.agent_registry import get as get_agent
    from core.cost_tracker import CostTracker
    from core.llm_router import LLMRouter
    from config.settings import settings

    org_id: str = test_org
    run_id = str(uuid.uuid4())

    router = LLMRouter(
        Path(__file__).parents[2] / "apps" / "api" / "config" / "model_tiers.yaml",
        CostTracker(),
        settings,
    )

    # Patch complete() to return the golden trace response and set cost attrs.
    async def _mock_complete(*_args, **_kwargs) -> str:
        router.last_tokens_used = 250
        router.last_cost_usd = 0.002
        return _GOLDEN["mock_llm_response"]

    router.complete = _mock_complete  # type: ignore[method-assign]

    agent = get_agent("keyword_research")

    async with org_session_for_test(db_engine, org_id) as db:
        ctx = AgentContext(
            org_id=org_id,
            run_id=run_id,
            params={"seed_keyword": "ai marketing"},
            config={},
            db=db,
            llm=router,
        )
        result = await agent.run(ctx)

    assert result.status == "success", f"Agent failed: {result.error}"
    assert result.data["keywords_found"] == 5

    # Verify keywords are in DB under the correct org
    async with org_session_for_test(db_engine, org_id) as db:
        kw_count = (await db.execute(text("SELECT COUNT(*) FROM keywords"))).scalar()
        assert kw_count == 5, f"Expected 5 keywords in DB, got {kw_count}"

        run_row = (
            await db.execute(
                text("SELECT status, cost_usd FROM agent_runs WHERE id = :rid"),
                {"rid": run_id},
            )
        ).fetchone()
        assert run_row is not None, "agent_runs row not written"
        assert run_row[0] == "success", f"agent_run.status = {run_row[0]!r}"
        assert run_row[1] > 0, f"agent_run.cost_usd should be > 0, got {run_row[1]}"

    # A different org must see zero rows (basic RLS check — full isolation in test 2)
    other_org_id = str(uuid.uuid4())
    async with org_session_for_test(db_engine, other_org_id) as db:
        other_count = (await db.execute(text("SELECT COUNT(*) FROM keywords"))).scalar()
    assert other_count == 0, (
        f"RLS failure: unrelated org sees {other_count} keywords belonging to {org_id}"
    )


# ── Test 2: RLS isolation (security gate) ────────────────────────────────────

async def test_rls_isolation(admin_db, db_engine):
    """Keywords written for org_a must not appear when querying as org_b.

    A failure here is a critical multi-tenant data leak and blocks all merges.
    """
    org_a_id = str(uuid.uuid4())
    org_b_id = str(uuid.uuid4())

    # Create both orgs (organizations table has no RLS)
    for oid, label in ((org_a_id, "org-a"), (org_b_id, "org-b")):
        await admin_db.execute(
            text(
                "INSERT INTO organizations (id, name, slug, supabase_user_id) "
                "VALUES (:id, :name, :slug, :suid)"
            ),
            {
                "id": oid,
                "name": f"RLS Test {label}",
                "slug": f"{label}-{oid[:8]}",
                "suid": str(uuid.uuid4()),
            },
        )
    await admin_db.commit()

    # Write one keyword row for org_a (INSERT unrestricted — no WITH CHECK on policy)
    async with org_session_for_test(db_engine, org_a_id) as db:
        await db.execute(
            text(
                "INSERT INTO keywords "
                "(id, org_id, keyword, status, source_agent, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :org_id, 'rls-test-keyword', "
                "'raw', 'test', now(), now())"
            ),
            {"org_id": org_a_id},
        )
        await db.commit()

    # org_a session must see exactly 1 row
    async with org_session_for_test(db_engine, org_a_id) as db:
        count_a = (await db.execute(text("SELECT COUNT(*) FROM keywords"))).scalar()
    assert count_a == 1, f"org_a should see 1 keyword, got {count_a}"

    # org_b session must see 0 rows — RLS policy blocks cross-org access
    async with org_session_for_test(db_engine, org_b_id) as db:
        count_b = (await db.execute(text("SELECT COUNT(*) FROM keywords"))).scalar()
    assert count_b == 0, (
        f"CRITICAL: org_b sees {count_b} row(s) belonging to org_a. "
        "Multi-tenant RLS is broken — block this merge immediately."
    )
