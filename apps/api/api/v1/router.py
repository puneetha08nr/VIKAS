from fastapi import APIRouter

from api.v1 import agents, chat, dashboard, keywords, orgs

router = APIRouter()

router.include_router(orgs.router)
router.include_router(agents.router)
router.include_router(keywords.router)
router.include_router(dashboard.router)
router.include_router(chat.router)
