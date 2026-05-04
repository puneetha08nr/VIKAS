from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class PromptNotFoundError(Exception):
    def __init__(self, agent_name: str) -> None:
        super().__init__(f"No active prompt found for agent '{agent_name}'")
        self.agent_name = agent_name


class PromptRegistry:

    async def get(self, agent_name: str, db: AsyncSession) -> str:
        """Return the active prompt template for an agent.

        Raises PromptNotFoundError if no active row exists — never falls back
        to hardcoded strings so missing prompts fail loudly.
        """
        result = await db.execute(
            text(
                "SELECT template FROM prompts "
                "WHERE agent_name = :agent_name AND active = true "
                "LIMIT 1"
            ),
            {"agent_name": agent_name},
        )
        row = result.fetchone()
        if row is None:
            raise PromptNotFoundError(agent_name)
        return str(row[0])

    async def set(self, agent_name: str, template: str, db: AsyncSession) -> int:
        """Insert a new active prompt version, deactivating any current one.

        Returns the new version number.
        """
        # Deactivate current active prompt
        await db.execute(
            text(
                "UPDATE prompts SET active = false "
                "WHERE agent_name = :agent_name AND active = true"
            ),
            {"agent_name": agent_name},
        )

        # Determine next version number
        result = await db.execute(
            text(
                "SELECT COALESCE(MAX(version), 0) FROM prompts "
                "WHERE agent_name = :agent_name"
            ),
            {"agent_name": agent_name},
        )
        next_version: int = int(result.scalar() or 0) + 1

        # Insert new active prompt
        await db.execute(
            text(
                "INSERT INTO prompts (id, agent_name, version, template, active, created_at) "
                "VALUES (gen_random_uuid(), :agent_name, :version, :template, true, now())"
            ),
            {"agent_name": agent_name, "version": next_version, "template": template},
        )
        await db.commit()
        return next_version

    async def rollback(self, agent_name: str, version: int, db: AsyncSession) -> bool:
        """Deactivate the current version and activate the specified one.

        Returns True if the target version was found and activated, False otherwise.
        """
        # Check the target version exists
        result = await db.execute(
            text(
                "SELECT id FROM prompts "
                "WHERE agent_name = :agent_name AND version = :version "
                "LIMIT 1"
            ),
            {"agent_name": agent_name, "version": version},
        )
        if result.fetchone() is None:
            return False

        # Deactivate current
        await db.execute(
            text(
                "UPDATE prompts SET active = false "
                "WHERE agent_name = :agent_name AND active = true"
            ),
            {"agent_name": agent_name},
        )

        # Activate target
        await db.execute(
            text(
                "UPDATE prompts SET active = true "
                "WHERE agent_name = :agent_name AND version = :version"
            ),
            {"agent_name": agent_name, "version": version},
        )
        await db.commit()
        return True

    async def history(self, agent_name: str, db: AsyncSession) -> list[dict]:
        """Return all versions for an agent, newest first."""
        result = await db.execute(
            text(
                "SELECT id, agent_name, version, template, active, created_at "
                "FROM prompts "
                "WHERE agent_name = :agent_name "
                "ORDER BY version DESC"
            ),
            {"agent_name": agent_name},
        )
        return [
            {
                "id": str(row[0]),
                "agent_name": row[1],
                "version": row[2],
                "template": row[3],
                "active": row[4],
                "created_at": row[5].isoformat() if row[5] else None,
            }
            for row in result.fetchall()
        ]
