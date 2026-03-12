"""
Instance provisioning orchestrator.
Coordinates Railway API calls to create a complete customer instance.
"""

import json
import uuid
import logging
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Template, Instance, BillingTxn
from app.security import encrypt_data, hash_password
from app.services.railway import RailwayClient, RailwayAPIError

logger = logging.getLogger(__name__)


class ProvisioningError(Exception):
    pass


def _build_env_vars(config: dict, template: Template) -> dict[str, str]:
    """
    Build the environment variables dict for the Railway service.
    Maps user-provided config to the env vars the template expects.
    """
    env_vars = {}

    # Map all user-provided variables
    for var_def in template.required_vars:
        var_name = var_def["name"]
        if var_name in config:
            env_vars[var_name] = config[var_name]

    # LLM provider routing
    llm_provider = config.get("LLM_PROVIDER", "anthropic")
    llm_api_key = config.get("LLM_API_KEY", "")
    llm_model = config.get("LLM_MODEL", "claude-sonnet-4-6")
    llm_base_url = config.get("LLM_BASE_URL", "")

    if llm_provider == "anthropic":
        env_vars["ANTHROPIC_API_KEY"] = llm_api_key
    elif llm_provider == "openai":
        env_vars["OPENAI_API_KEY"] = llm_api_key
    elif llm_provider == "google":
        env_vars["GOOGLE_API_KEY"] = llm_api_key
    elif llm_provider in ("ollama", "huggingface", "custom"):
        # OpenAI-compatible endpoint
        if llm_api_key:
            env_vars["OPENAI_API_KEY"] = llm_api_key
        if llm_base_url:
            env_vars["OPENAI_BASE_URL"] = llm_base_url

    # Admin API key for the instance
    if "ADMIN_API_KEY" in config:
        env_vars["ADMIN_API_KEY"] = config["ADMIN_API_KEY"]

    # Volume path
    env_vars["GENERATIONS_DIR"] = "/data/generations"

    # Default model override
    if llm_model:
        env_vars["DEFAULT_MODEL"] = llm_model

    return env_vars


async def provision_instance(
    db: AsyncSession,
    user: User,
    template: Template,
    config: dict,
    instance_name: str | None = None,
) -> Instance:
    """
    Full provisioning flow:
    1. Validate credits
    2. Create DB record
    3. Create Railway project + service + volume + vars + domain
    4. Trigger deploy
    5. Update DB with Railway IDs
    """
    railway = RailwayClient()

    # 1. Validate user has enough credits
    min_credits = Decimal("4.0")
    if user.credits < min_credits:
        raise ProvisioningError(
            f"Insufficient credits. Need {min_credits}, have {user.credits}. "
            f"Please top up before creating an instance."
        )

    # 2. Create instance record
    instance = Instance(
        user_id=user.id,
        template_id=template.id,
        name=instance_name or f"{template.name} - {user.display_name}",
        encrypted_vars=encrypt_data(json.dumps({
            k: v for k, v in config.items()
            if k not in ("ADMIN_API_KEY",)  # Don't store admin key in encrypted vars
        })),
        admin_api_key_hash=hash_password(config.get("ADMIN_API_KEY", "")),
        llm_provider=config.get("LLM_PROVIDER", "anthropic"),
        llm_model=config.get("LLM_MODEL", "claude-sonnet-4-6"),
        status="provisioning",
    )
    db.add(instance)
    await db.flush()  # Get the ID

    short_id = str(instance.id)[:8]
    project_name = f"ao-{str(user.id)[:8]}-{short_id}"

    try:
        # 3. Create Railway project
        logger.info(f"Creating Railway project: {project_name}")
        project = await railway.create_project(
            name=project_name,
            description=f"Agent instance for {user.email} ({template.name})",
        )
        instance.railway_project_id = project["id"]

        # 4. Get default environment
        envs = await railway.get_environments(project["id"])
        if not envs:
            raise ProvisioningError("No environments found in new project")
        env_id = envs[0]["id"]
        instance.railway_environment_id = env_id

        # 5. Create service
        logger.info(f"Creating service from repo: {template.github_repo}")
        service = await railway.create_service(project["id"], "harness")
        instance.railway_service_id = service["id"]

        # 6. Connect to GitHub repo
        await railway.connect_service_to_repo(
            service["id"], template.github_repo, template.github_branch
        )

        # 7. Create volume (needs serviceId)
        logger.info("Creating persistent volume")
        await railway.create_volume(project["id"], env_id, service["id"])

        # 8. Set environment variables
        env_vars = _build_env_vars(config, template)
        logger.info(f"Setting {len(env_vars)} environment variables")
        await railway.upsert_variables(project["id"], env_id, service["id"], env_vars)

        # 9. Create public domain
        logger.info("Creating public domain")
        domain = await railway.create_service_domain(service["id"], env_id)
        instance.railway_domain = domain["domain"]

        # 10. Trigger deploy
        logger.info("Triggering deployment")
        await railway.deploy_service(service["id"], env_id)

        instance.status = "deploying"
        logger.info(f"Instance {instance.id} provisioned successfully: https://{domain['domain']}")

    except RailwayAPIError as e:
        logger.error(f"Railway API error during provisioning: {e}")
        instance.status = "error"
        instance.error_message = str(e)
        # Attempt cleanup
        if instance.railway_project_id:
            try:
                await railway.delete_project(instance.railway_project_id)
            except Exception:
                logger.error("Failed to cleanup Railway project after error")

    except Exception as e:
        logger.error(f"Unexpected error during provisioning: {e}")
        instance.status = "error"
        instance.error_message = str(e)

    return instance


async def deprovision_instance(db: AsyncSession, instance: Instance) -> bool:
    """
    Delete all Railway resources for an instance.
    """
    railway = RailwayClient()

    if instance.railway_project_id:
        try:
            await railway.delete_project(instance.railway_project_id)
            logger.info(f"Deleted Railway project {instance.railway_project_id}")
        except RailwayAPIError as e:
            logger.error(f"Failed to delete Railway project: {e}")
            return False

    instance.status = "deleted"
    instance.railway_project_id = None
    instance.railway_service_id = None
    instance.railway_domain = None

    return True
