"""Tenant Manager Server.

Control-plane backend for tenant lifecycle P0.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.config import get_settings
from apps.shared.core.exception_handlers import register_exception_handlers
from apps.shared.core.request_context import RequestLoggingMiddleware
from apps.shared.utils.logger import get_logger
from apps.tenant_manager_service.routers import auth, health, tenants, users

logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize tenant manager runtime resources."""
    logger.info("Tenant Manager Server startup")
    yield
    logger.info("Tenant Manager Server shutdown")


app = FastAPI(
    title="LingQing Tenant Manager",
    description="Control plane service for tenant lifecycle operations",
    version=settings.API_VERSION,
    lifespan=lifespan,
)

register_exception_handlers(app)

app.add_middleware(RequestLoggingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(tenants.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "LingQing Tenant Manager",
        "version": settings.API_VERSION,
        "service": "tenant-manager",
    }
