"""
Application configuration from environment variables.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/orchestrator"

    # Auth
    jwt_secret: str = "CHANGE-ME-IN-PRODUCTION-USE-64-RANDOM-CHARS"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24

    # Encryption for customer API keys at rest
    fernet_key: str = ""  # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

    # Railway API (for provisioning customer instances)
    railway_api_token: str = ""
    railway_workspace_id: str = ""
    railway_api_url: str = "https://backboard.railway.com/graphql/v2"

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # Platform
    platform_domain: str = "http://localhost:8000"
    admin_email: str = "admin@localhost"

    # Limits
    max_instances_per_user: int = 10
    min_credits_for_instance: float = 4.0  # Minimum 4 sprints to create instance

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
