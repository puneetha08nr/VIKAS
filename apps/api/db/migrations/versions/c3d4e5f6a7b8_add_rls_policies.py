"""add row-level security policies to all org-scoped tables

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-29 00:00:00.000000

Each org-scoped table gets:
  ENABLE ROW LEVEL SECURITY   — activates the RLS machinery
  FORCE ROW LEVEL SECURITY    — applies policies even to table owners / superusers
  POLICY org_isolation        — SELECT/UPDATE/DELETE see only the current org's rows
                                INSERT is intentionally unrestricted (agents always
                                supply org_id explicitly; adding WITH CHECK here
                                would complicate admin tooling without security benefit
                                since the INSERT path is never user-controlled)

The session variable app.current_org_id is set by db.session.org_session() before
every query. Callers without the variable set see zero rows.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables with an org_id column that must be tenant-isolated.
# organizations and prompts are intentionally excluded:
#   organizations — is the root tenant table; looked up via JWT, not RLS
#   prompts       — global (no org_id column)
_ORG_SCOPED_TABLES = [
    "keyword_clusters",
    "keywords",
    "opportunities",
    "content_items",
    "content_reviews",
    "competitors",
    "competitor_content",
    "trend_signals",
    "knowledge_chunks",
    "brand_voice",
    "preferences",
    "agent_runs",
    "pipeline_runs",
]


def upgrade() -> None:
    for table in _ORG_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY org_isolation ON {table}
            USING (
                org_id::text = current_setting('app.current_org_id', true)
            )
        """)


def downgrade() -> None:
    for table in reversed(_ORG_SCOPED_TABLES):
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
