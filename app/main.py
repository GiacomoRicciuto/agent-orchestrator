"""
Agent Orchestrator — Main FastAPI application.

Platform for automated provisioning and management of AI agent microservice instances.
Each customer gets an isolated, self-improving instance deployed on Railway.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.routers import auth, marketplace, instances, billing

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("orchestrator")

# ── App Lifecycle ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    import os

    logger.info("Starting Agent Orchestrator...")
    logger.info(f"  PORT={os.environ.get('PORT', 'not set')}")
    logger.info(f"  DATABASE_URL={'set' if os.environ.get('DATABASE_URL') else 'NOT SET'}")
    logger.info(f"  DATABASE_PUBLIC_URL={'set' if os.environ.get('DATABASE_PUBLIC_URL') else 'not set'}")
    logger.info(f"  JWT_SECRET={'set' if os.environ.get('JWT_SECRET') else 'NOT SET (using default)'}")
    logger.info(f"  FERNET_KEY={'set' if os.environ.get('FERNET_KEY') else 'NOT SET'}")
    logger.info(f"  RAILWAY_API_TOKEN={'set' if os.environ.get('RAILWAY_API_TOKEN') else 'not set'}")

    # Retry DB connection (Railway DB may take a moment to be ready)
    db_ready = False
    for attempt in range(15):
        try:
            await init_db()
            logger.info("Database initialized successfully")
            db_ready = True
            break
        except Exception as e:
            if attempt < 14:
                logger.warning(f"Database not ready (attempt {attempt + 1}/15): {type(e).__name__}: {e}")
                await asyncio.sleep(2)
            else:
                logger.error(f"Failed to connect to database after 15 attempts: {e}")
                # Don't crash — let the health endpoint report the issue
                app.state.db_error = str(e)

    if db_ready:
        try:
            await seed_templates()
            logger.info("Templates seeded")
        except Exception as e:
            logger.error(f"Failed to seed templates: {e}")

    yield
    logger.info("Shutting down Agent Orchestrator")


app = FastAPI(
    title="Agent Orchestrator",
    description="Platform for provisioning AI agent microservice instances",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────

settings = get_settings()
_cors_origins = [settings.platform_domain, "http://localhost:8000", "http://localhost:3000"]
# Add Railway domain if available
import os as _os
_railway_domain = _os.environ.get("RAILWAY_PUBLIC_DOMAIN")
if _railway_domain:
    _cors_origins.append(f"https://{_railway_domain}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Security Headers ──────────────────────────────────────────────────────────

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Server"] = "Agent-Orchestrator"
    return response

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(marketplace.router)
app.include_router(instances.router)
app.include_router(billing.router)

# ── Frontend ──────────────────────────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.get("/")
async def serve_frontend():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Agent Orchestrator API", "docs": "/docs"}


# ── Template Seeding ──────────────────────────────────────────────────────────

async def seed_templates():
    """Seed the marketplace with initial templates if empty."""
    import json
    from sqlalchemy import select, func
    from app.database import _get_session_factory
    from app.models import Template

    seed_file = Path(__file__).parent.parent / "seed" / "templates.json"
    if not seed_file.exists():
        logger.warning("No seed/templates.json found, skipping template seeding")
        return

    factory = _get_session_factory()
    async with factory() as session:
        result = await session.execute(select(func.count(Template.id)))
        count = result.scalar()
        if count > 0:
            logger.info(f"Templates already seeded ({count} found)")
            return

        templates_data = json.loads(seed_file.read_text())
        for t in templates_data:
            template = Template(**t)
            session.add(template)
        await session.commit()
        logger.info(f"Seeded {len(templates_data)} templates")


# ── Health Check ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    db_error = getattr(app.state, "db_error", None)
    if db_error:
        return {"status": "degraded", "service": "agent-orchestrator", "db_error": db_error}
    return {"status": "ok", "service": "agent-orchestrator"}


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=os.environ.get("DEV") == "1")
