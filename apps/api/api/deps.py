import logging
from collections.abc import AsyncGenerator

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from db.models.organizations import Organization
from db.session import AsyncSessionLocal, org_session

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


async def _verify_supabase_token(token: str) -> str:
    """Call Supabase /auth/v1/user, raise 401 on failure, return supabase user id."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.supabase_url}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": settings.supabase_service_role_key,
            },
            timeout=10.0,
        )

    if resp.status_code != 200:
        logger.warning(
            "Supabase token verification failed: status=%d body=%s",
            resp.status_code,
            resp.text[:200],
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    uid: str = resp.json().get("id", "")
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not extract user ID from token",
        )
    return uid


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    """Verify Supabase JWT and return supabase_user_id."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No token")
    return await _verify_supabase_token(credentials.credentials)


async def get_current_org(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> Organization:
    """Verify Supabase JWT and return the caller's Organization.

    In development with DEV_AUTH_BYPASS=true, skips Supabase and returns the
    first org in the DB — no token required.
    """
    if settings.dev_auth_bypass and settings.is_dev:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Organization).limit(1))
            org = result.scalar_one_or_none()
        if org is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No organization found (dev bypass active — seed the DB first)",
            )
        return org

    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No token")

    supabase_user_id = await _verify_supabase_token(credentials.credentials)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Organization).where(Organization.supabase_user_id == supabase_user_id)
        )
        org = result.scalar_one_or_none()

    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    return org


async def get_db_for_org(
    org: Organization = Depends(get_current_org),
) -> AsyncGenerator[AsyncSession, None]:
    """Yield an RLS-scoped AsyncSession pinned to the caller's org."""
    async with org_session(str(org.id)) as session:
        yield session
