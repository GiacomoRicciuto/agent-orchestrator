"""
Marketplace routes: list available templates.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Template
from app.dependencies import get_current_user, User

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


class TemplateResponse(BaseModel):
    id: str
    slug: str
    name: str
    description: str | None
    icon: str | None
    category: str | None
    required_vars: list[dict]
    llm_options: list[dict] | None
    cost_per_sprint: float


@router.get("/templates", response_model=list[TemplateResponse])
async def list_templates(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Template).where(Template.is_active == True).order_by(Template.name)
    )
    templates = result.scalars().all()

    return [
        TemplateResponse(
            id=str(t.id),
            slug=t.slug,
            name=t.name,
            description=t.description,
            icon=t.icon,
            category=t.category,
            required_vars=t.required_vars,
            llm_options=t.llm_options,
            cost_per_sprint=float(t.cost_per_sprint),
        )
        for t in templates
    ]
