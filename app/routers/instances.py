"""
Instance management routes: create, list, status, delete.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, Template, Instance
from app.dependencies import get_current_user
from app.services.provisioner import provision_instance, deprovision_instance, ProvisioningError
from app.config import get_settings

router = APIRouter(prefix="/api/instances", tags=["instances"])


class CreateInstanceRequest(BaseModel):
    template_id: str
    name: str | None = None
    config: dict  # All API keys + LLM config


class InstanceResponse(BaseModel):
    id: str
    name: str | None
    template_name: str
    template_icon: str | None
    llm_provider: str | None
    llm_model: str | None
    status: str
    domain: str | None
    sprints_used: int
    error_message: str | None
    created_at: str


@router.post("/", response_model=InstanceResponse)
async def create_instance(
    req: CreateInstanceRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()

    # Check instance limit
    result = await db.execute(
        select(Instance).where(
            Instance.user_id == user.id,
            Instance.status.notin_(["deleted", "error"]),
        )
    )
    active_instances = result.scalars().all()
    if len(active_instances) >= settings.max_instances_per_user:
        raise HTTPException(status_code=400, detail=f"Maximum {settings.max_instances_per_user} active instances allowed")

    # Get template
    import uuid as _uuid
    result = await db.execute(select(Template).where(Template.id == _uuid.UUID(req.template_id)))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Validate required vars
    for var_def in template.required_vars:
        if var_def.get("required", True) and var_def["name"] not in req.config:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required variable: {var_def['name']} ({var_def.get('label', '')})",
            )

    # Validate ADMIN_API_KEY is set
    if not req.config.get("ADMIN_API_KEY"):
        raise HTTPException(status_code=400, detail="ADMIN_API_KEY (instance password) is required")

    try:
        instance = await provision_instance(db, user, template, req.config, req.name)
    except ProvisioningError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return InstanceResponse(
        id=str(instance.id),
        name=instance.name,
        template_name=template.name,
        template_icon=template.icon,
        llm_provider=instance.llm_provider,
        llm_model=instance.llm_model,
        status=instance.status,
        domain=f"https://{instance.railway_domain}" if instance.railway_domain else None,
        sprints_used=instance.sprints_used,
        error_message=instance.error_message,
        created_at=instance.created_at.isoformat(),
    )


@router.get("/", response_model=list[InstanceResponse])
async def list_instances(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Instance)
        .where(Instance.user_id == user.id, Instance.status != "deleted")
        .order_by(Instance.created_at.desc())
    )
    instances = result.scalars().all()

    responses = []
    for inst in instances:
        # Lazy-load template
        t_result = await db.execute(select(Template).where(Template.id == inst.template_id))
        template = t_result.scalar_one_or_none()

        responses.append(InstanceResponse(
            id=str(inst.id),
            name=inst.name,
            template_name=template.name if template else "Unknown",
            template_icon=template.icon if template else None,
            llm_provider=inst.llm_provider,
            llm_model=inst.llm_model,
            status=inst.status,
            domain=f"https://{inst.railway_domain}" if inst.railway_domain else None,
            sprints_used=inst.sprints_used,
            error_message=inst.error_message,
            created_at=inst.created_at.isoformat(),
        ))

    return responses


@router.get("/{instance_id}", response_model=InstanceResponse)
async def get_instance(
    instance_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import uuid as _uuid
    result = await db.execute(
        select(Instance).where(Instance.id == _uuid.UUID(instance_id), Instance.user_id == user.id)
    )
    inst = result.scalar_one_or_none()
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")

    t_result = await db.execute(select(Template).where(Template.id == inst.template_id))
    template = t_result.scalar_one_or_none()

    return InstanceResponse(
        id=str(inst.id),
        name=inst.name,
        template_name=template.name if template else "Unknown",
        template_icon=template.icon if template else None,
        llm_provider=inst.llm_provider,
        llm_model=inst.llm_model,
        status=inst.status,
        domain=f"https://{inst.railway_domain}" if inst.railway_domain else None,
        sprints_used=inst.sprints_used,
        error_message=inst.error_message,
        created_at=inst.created_at.isoformat(),
    )


@router.delete("/{instance_id}")
async def delete_instance(
    instance_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import uuid as _uuid
    result = await db.execute(
        select(Instance).where(Instance.id == _uuid.UUID(instance_id), Instance.user_id == user.id)
    )
    inst = result.scalar_one_or_none()
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")

    success = await deprovision_instance(db, inst)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete Railway resources")

    return {"ok": True, "message": "Instance deleted"}
