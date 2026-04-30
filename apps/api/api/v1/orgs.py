from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_org, get_db_for_org, verify_token
from config.settings import settings
from db.models.brand_voice import BrandVoice
from db.models.organizations import Organization
from db.session import AsyncSessionLocal

router = APIRouter(prefix="/orgs", tags=["orgs"])


class OrgCreate(BaseModel):
    name: str
    slug: str
    supabase_user_id: str  # must match the verified JWT — server enforces this


class OrgSettingsUpdate(BaseModel):
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    wordpress_url: str | None = None


def _mask_key(key: str) -> str:
    if len(key) <= 7:
        return "***"
    return key[:3] + "..." + key[-4:]


def _masked_settings(fernet: Fernet, stored: dict) -> dict:
    out: dict = {}
    for field in ("openai_api_key", "anthropic_api_key"):
        if field in stored:
            try:
                out[field] = _mask_key(fernet.decrypt(stored[field].encode()).decode())
            except Exception:
                out[field] = "***"
    if "wordpress_url" in stored:
        out["wordpress_url"] = stored["wordpress_url"]
    return out


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_org(
    body: OrgCreate,
    jwt_user_id: str = Depends(verify_token),
) -> dict:
    """Create an org for a newly signed-up user.

    The supabase_user_id stored in the DB always comes from the verified JWT,
    not the request body, so a caller cannot claim another user's identity.
    """
    if body.supabase_user_id != jwt_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="supabase_user_id in body does not match the authenticated user",
        )

    org = Organization(name=body.name, slug=body.slug, supabase_user_id=jwt_user_id)

    async with AsyncSessionLocal() as session:
        try:
            session.add(org)
            await session.flush()
            session.add(BrandVoice(org_id=org.id))
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An organization with this slug or Supabase user ID already exists",
            )

    return {"org_id": str(org.id), "name": org.name, "slug": org.slug}


@router.get("/me")
async def get_me(org: Organization = Depends(get_current_org)) -> dict:
    return {
        "org_id": str(org.id),
        "name": org.name,
        "slug": org.slug,
        "created_at": org.created_at,
    }


@router.put("/me/settings")
async def update_settings(
    body: OrgSettingsUpdate,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> dict:
    fernet = Fernet(settings.settings_encryption_key.encode())

    result = await db.execute(select(Organization).where(Organization.id == org.id))
    db_org = result.scalar_one()

    current = dict(db_org.settings or {})

    if body.openai_api_key is not None:
        current["openai_api_key"] = fernet.encrypt(body.openai_api_key.encode()).decode()
    if body.anthropic_api_key is not None:
        current["anthropic_api_key"] = fernet.encrypt(body.anthropic_api_key.encode()).decode()
    if body.wordpress_url is not None:
        current["wordpress_url"] = body.wordpress_url

    await db.execute(
        sa_update(Organization).where(Organization.id == org.id).values(settings=current)
    )
    await db.commit()

    return _masked_settings(fernet, current)
