"""create vikas_app role for RLS-enforced application connections

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-04-29 00:00:00.000000

PostgreSQL superusers bypass RLS even with FORCE ROW LEVEL SECURITY.
The application must connect (or SET ROLE) as a non-superuser role so that
the org_isolation policies on every table actually take effect.

vikas_app has full DML permissions but no superuser/bypass-RLS attributes,
so it is subject to all RLS policies just like a real end-user session.

Production: configure DATABASE_URL to use vikas_app credentials.
Tests:      use SET ROLE vikas_app inside each org-scoped test session.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Idempotent: CREATE ROLE only if it does not already exist.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'vikas_app') THEN
                CREATE ROLE vikas_app NOLOGIN;
            END IF;
        END
        $$
    """)

    op.execute("GRANT USAGE ON SCHEMA public TO vikas_app")
    op.execute("GRANT ALL ON ALL TABLES IN SCHEMA public TO vikas_app")
    op.execute("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO vikas_app")

    # Ensure tables and sequences created by future migrations are also covered.
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT ALL ON TABLES TO vikas_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT ALL ON SEQUENCES TO vikas_app"
    )


def downgrade() -> None:
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE ALL ON SEQUENCES FROM vikas_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE ALL ON TABLES FROM vikas_app"
    )
    op.execute("DROP ROLE IF EXISTS vikas_app")
