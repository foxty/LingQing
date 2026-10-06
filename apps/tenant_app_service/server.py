"""LingQing Backend Server.

Unified FastAPI server for:
- Tenant management and resource administration (auth, tenants, documents, data sources)
- Chat and agent orchestration (chat, threads)

Development:
    uv run uvicorn apps.tenant_app_service.server:app --reload --port 8000

Production:
    uvicorn apps.tenant_app_service.server:app --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from apps.config import get_settings, get_static_path
from apps.shared.core.exception_handlers import register_exception_handlers
from apps.shared.core.request_context import RequestLoggingMiddleware
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agent_catalog.router import router as agents_router
from apps.tenant_app_service.agent_ingress.slack.agent_router import router as slack_agent_router
from apps.tenant_app_service.agent_ingress.slack.identity_router import router as slack_identity_router
from apps.tenant_app_service.agent_ingress.slack.ingress_router import router as slack_ingress_router
from apps.tenant_app_service.agent_pool import get_agent_pool
from apps.tenant_app_service.identity.router import router as identity_router
from apps.tenant_app_service.routers import (
    abac,
    acl_shares,
    admin_system_tasks,
    api_connectors,
    auth,
    charts,
    chat,
    context_resources,
    dashboard,
    data_sources,
    document_collections,
    document_sources,
    document_sync,
    documents,
    health,
    hitl,
    live_apps,
    llm_config,
    message_feedback,
    notifications,
    observability,
    reports,
    scheduled_tasks,
    search,
    skills,
    tags,
    tenants,
    threads,
    users,
)
from apps.tenant_app_service.sso.router import router as sso_router

# Initialize logger
logger = get_logger(__name__)

# Get settings
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifespan: startup and shutdown."""
    # Startup
    get_agent_pool()
    logger.info("Agent pool initialized")
    logger.info("LingQing Backend Server started successfully")

    yield

    # Shutdown
    logger.info("LingQing Backend Server shutdown")


# Initialize FastAPI app
app = FastAPI(
    title="LingQing Backend",
    description="Unified backend service for tenant management, chat, and agent orchestration",
    version=settings.API_VERSION,
    lifespan=lifespan,
)

logger.info("Initializing LingQing Backend Server")

# Register exception handlers
register_exception_handlers(app)
logger.info("Exception handlers registered")

app.add_middleware(RequestLoggingMiddleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory=get_static_path()), name="static")


# Register routers - order matters for middleware execution
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(tenants.router)
app.include_router(documents.router)
app.include_router(document_collections.router)
app.include_router(document_sources.router)
app.include_router(document_sync.router)
app.include_router(data_sources.router)
app.include_router(api_connectors.router)
app.include_router(search.router)
app.include_router(context_resources.router)
app.include_router(dashboard.router)
app.include_router(charts.router)
app.include_router(tags.router)
app.include_router(abac.router)
app.include_router(observability.router)
app.include_router(reports.router)
app.include_router(notifications.router)
app.include_router(admin_system_tasks.router)
app.include_router(scheduled_tasks.router)
app.include_router(chat.router)
app.include_router(hitl.router)
app.include_router(message_feedback.router)
app.include_router(threads.router)
app.include_router(acl_shares.router)
app.include_router(users.router)
app.include_router(live_apps.router)
app.include_router(live_apps.v1_router)
app.include_router(llm_config.router)
app.include_router(skills.router)
app.include_router(agents_router)
app.include_router(identity_router)
app.include_router(sso_router)
app.include_router(slack_identity_router)
app.include_router(slack_agent_router)
app.include_router(slack_ingress_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "LingQing Backend",
        "version": settings.API_VERSION,
        "service": "backend",
    }
