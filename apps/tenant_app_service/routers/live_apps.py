"""Live app runtime routes."""

import mimetypes
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.api_connector.execution import ApiConnectorExecutionService
from apps.shared.api_connector.schemas import (
    ApiOperationCallRequest,
    ApiOperationCallResponse,
)
from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import get_current_user, require_permission
from apps.shared.db.session import get_db
from apps.shared.domain.actor import ActorContext
from apps.shared.live_app.schemas import (
    LiveAppListDTO,
    LiveAppMutateRequestDTO,
    LiveAppQueryRequestDTO,
    LiveAppRecordDTO,
)
from apps.shared.live_app.service import LiveAppService
from apps.shared.schemas.user import UserDTO

router = APIRouter(prefix="/apps", tags=["live-apps"])
v1_router = APIRouter(prefix="/apps/v1", tags=["live-apps"])
_SDK_ROOT = Path(__file__).resolve().parent / "sdk"


def _actor_ctx(current_user: UserDTO) -> ActorContext:
    return ActorContext(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        user_role=current_user.role,
    )


_VENDOR_ROOT = _SDK_ROOT / "vendor"


@lru_cache(maxsize=8)
def _discover_vendor_asset(prefix: str) -> str | None:
    """Find latest vendored file matching prefix (e.g. 'tailwind' -> 'tailwind-3.4.17.js')."""
    if not _VENDOR_ROOT.is_dir():
        return None
    matches = sorted(
        (f.name for f in _VENDOR_ROOT.iterdir() if f.name.startswith(prefix) and f.suffix == ".js"),
        reverse=True,
    )
    return matches[0] if matches else None


def _inject_sdk_once(html: str, sdk_version: str, app_id: int, environment: str) -> str:
    sdk_tag = f'<script src="/api/apps/sdk/lq-sdk.v{sdk_version}.js"></script>'
    if sdk_tag in html:
        return html

    tailwind_file = _discover_vendor_asset("tailwind")
    alpine_file = _discover_vendor_asset("alpine")

    lines = []
    if tailwind_file:
        lines.append(f'  <script src="/api/apps/sdk/vendor/{tailwind_file}"></script>')
    if alpine_file:
        lines.append(f'  <script defer src="/api/apps/sdk/vendor/{alpine_file}"></script>')
    lines.append(f"  {sdk_tag}")
    lines.append(
        "  <script>"
        f"window.LQ=window.LQ||{{}};"
        f'window.LQ.liveApp=window.LQ.createLiveAppClient({{appId:{app_id},environment:"{environment}"}});'
        "</script>"
    )

    snippet = "\n".join(lines) + "\n"
    if "</head>" in html:
        return html.replace("</head>", f"{snippet}</head>", 1)
    return f"{snippet}{html}"


@lru_cache(maxsize=8)
def _load_live_app_sdk(sdk_version: str) -> str:
    sdk_path = _SDK_ROOT / f"lq-sdk.v{sdk_version}.js"
    if not sdk_path.exists():
        raise HTTPException(status_code=404, detail=f"Live app SDK version '{sdk_version}' not found")
    return sdk_path.read_text(encoding="utf-8")


def _resolve_sdk_version(requested_version: str) -> str:
    sdk_path = _SDK_ROOT / f"lq-sdk.v{requested_version}.js"
    if not sdk_path.exists():
        raise HTTPException(status_code=404, detail=f"Live app SDK version '{requested_version}' not found")
    return requested_version


def _api_meta() -> dict:
    return {
        "request_id": str(uuid4()),
        "api_version": "v1",
    }


def _asset_media_type(path: str) -> str:
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


_NO_CACHE_ENVIRONMENTS = frozenset({"dev", "test"})


def _app_cache_headers(environment: str) -> dict[str, str]:
    if environment in _NO_CACHE_ENVIRONMENTS:
        return {"Cache-Control": "no-store"}
    return {"Cache-Control": "public, max-age=300"}


def _is_disallowed_asset_path(path: str) -> bool:
    normalized = (path or "").strip().strip("/")
    if not normalized:
        return True
    # Keep migration SQL files and reserved route names non-web-addressable.
    if normalized.startswith("migrations/") or normalized.endswith(".sql"):
        return True
    if normalized in {"entry", "embed"}:
        return True
    return False


@router.get("/sdk/playground")
async def get_sdk_playground():
    """Serve SDK component playground page for manual verification."""
    playground_path = _SDK_ROOT / "playground.html"
    if not playground_path.exists():
        raise HTTPException(status_code=404, detail="Playground not found")
    return Response(content=playground_path.read_text(encoding="utf-8"), media_type="text/html")


@router.get("/sdk/lq-sdk.v{sdk_version}.js")
async def get_live_app_sdk(sdk_version: str):
    """Serve runtime JS SDK for live apps."""
    return Response(
        content=_load_live_app_sdk(sdk_version=sdk_version),
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/sdk/vendor/{filename}")
async def get_sdk_vendor_asset(filename: str):
    """Serve vendored third-party assets (Tailwind, Alpine)."""
    safe_name = Path(filename).name
    path = _VENDOR_ROOT / safe_name
    if not path.exists() or not path.suffix == ".js":
        raise HTTPException(status_code=404, detail="Vendor asset not found")
    return Response(
        content=path.read_text(encoding="utf-8"),
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/{app_id}/{environment}/entry")
async def get_live_app_entry(
    app_id: int,
    environment: str,
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Serve renderable live app HTML."""
    service = LiveAppService.create(tenant_id=current_user.tenant_id, db_session=db)
    entry = await service.get_entry_page_for_actor(
        app_id=app_id,
        actor=_actor_ctx(current_user),
        environment=environment,
    )
    resolved_sdk_version = _resolve_sdk_version(entry["sdk_version"])
    html_with_sdk = _inject_sdk_once(
        entry["html"], sdk_version=resolved_sdk_version, app_id=app_id, environment=environment
    )
    return Response(content=html_with_sdk, media_type="text/html", headers=_app_cache_headers(environment))


@router.get("/{app_id}/{environment}/embed")
async def get_live_app_embed(
    app_id: int,
    environment: str,
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Serve renderable live app HTML for iframe embedding."""
    service = LiveAppService.create(tenant_id=current_user.tenant_id, db_session=db)
    entry = await service.get_entry_page_for_actor(
        app_id=app_id,
        actor=_actor_ctx(current_user),
        environment=environment,
    )
    resolved_sdk_version = _resolve_sdk_version(entry["sdk_version"])
    html_with_sdk = _inject_sdk_once(
        entry["html"], sdk_version=resolved_sdk_version, app_id=app_id, environment=environment
    )
    return Response(content=html_with_sdk, media_type="text/html", headers=_app_cache_headers(environment))


@router.get("")
async def list_live_apps(
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List live apps accessible to the current user."""
    service = LiveAppService.create(tenant_id=current_user.tenant_id, db_session=db)
    dto: LiveAppListDTO = await service.list_apps_for_actor(actor=_actor_ctx(current_user))
    return {"data": dto.model_dump(), "meta": _api_meta()}


@router.get("/{app_id}")
async def get_live_app(
    app_id: int,
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get one live app metadata for current tenant."""
    service = LiveAppService.create(tenant_id=current_user.tenant_id, db_session=db)
    dto: LiveAppRecordDTO = await service.get_app_for_actor(app_id=app_id, actor=_actor_ctx(current_user))
    return {"data": dto.model_dump(), "meta": _api_meta()}


@router.get("/{app_id}/environments/diff")
async def diff_live_app_environments(
    app_id: int,
    from_environment: str = "dev",
    to_environment: str = "prod",
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Diff two live app environments and return drift summary."""
    service = LiveAppService.create(tenant_id=current_user.tenant_id, db_session=db)
    diff_payload = await service.diff_environments_for_actor(
        app_id=app_id,
        actor=_actor_ctx(current_user),
        from_environment=from_environment,
        to_environment=to_environment,
    )
    return {"data": diff_payload, "meta": _api_meta()}


async def _query_live_app_data_impl(
    app_id: int,
    environment: str,
    request: LiveAppQueryRequestDTO,
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run app-scoped read query for live app."""
    service = LiveAppService.create(tenant_id=current_user.tenant_id, db_session=db)
    data = await service.query_data_for_actor(
        app_id=app_id,
        actor=_actor_ctx(current_user),
        sql=request.sql,
        environment=environment,
    )
    return {"data": data, "meta": _api_meta()}


@v1_router.post("/{app_id}/{environment}/data/query")
async def query_live_app_data_v1(
    app_id: int,
    environment: str,
    request: LiveAppQueryRequestDTO,
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _query_live_app_data_impl(
        app_id=app_id,
        environment=environment,
        request=request,
        current_user=current_user,
        db=db,
    )


@v1_router.post("/{app_id}/{environment}/data/mutate")
async def mutate_live_app_data_v1(
    app_id: int,
    environment: str,
    request: LiveAppMutateRequestDTO,
    current_user: UserDTO = Depends(require_permission(Permissions.APPS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    service = LiveAppService.create(tenant_id=current_user.tenant_id, db_session=db)
    data = await service.mutate_data_for_actor(
        app_id=app_id,
        actor=_actor_ctx(current_user),
        operation=request.operation,
        table=request.table,
        data=request.data,
        where=request.where,
        row_id=request.id,
        environment=environment,
    )
    return {"data": data, "meta": _api_meta()}


@v1_router.post("/{app_id}/{environment}/data/import")
async def import_live_app_data_v1(
    app_id: int,
    environment: str,
    table: str = Form(...),
    mode: str = Form(...),
    file: UploadFile = File(...),
    current_user: UserDTO = Depends(require_permission(Permissions.APPS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    service = LiveAppService.create(tenant_id=current_user.tenant_id, db_session=db)
    file_content = await file.read()
    data = await service.import_data_for_actor(
        app_id=app_id,
        actor=_actor_ctx(current_user),
        table=table,
        mode=mode,
        file_name=file.filename or "import.csv",
        file_content=file_content,
        environment=environment,
    )
    return {"data": data, "meta": _api_meta()}


@v1_router.post("/{app_id}/{environment}/api-connectors/{operation_uid}/call", response_model=ApiOperationCallResponse)
async def call_api_connector_v1(
    app_id: int,
    environment: str,
    operation_uid: str,
    payload: ApiOperationCallRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.APPS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Call external API through connector, scoped to app context.

    Uses operation_uid (stable identifier) instead of operation_id (DB primary key).

    Validates:
    - App exists and user has access
    - Connector belongs to same tenant
    - Operation is active
    Returns execution result with status, body, headers, timing
    """
    # Verify app access
    service = LiveAppService.create(tenant_id=current_user.tenant_id, db_session=db)
    await service.require_read_access(app_id=app_id, actor=_actor_ctx(current_user))

    # Execute via ApiConnectorExecutionService (already uses operation_uid)
    exec_service = ApiConnectorExecutionService(tenant_id=current_user.tenant_id, db_session=db)
    result = await exec_service.execute_operation_for_actor(
        operation_uid=operation_uid,
        actor=_actor_ctx(current_user),
        parameters=payload.parameters,
    )
    return ApiOperationCallResponse(
        status_code=result.status_code,
        body=result.body,
        headers=result.headers,
        elapsed_ms=result.elapsed_ms,
        error=result.error,
    )


@router.get("/{app_id}/{environment}/{asset_path:path}")
async def get_live_app_asset(
    app_id: int,
    environment: str,
    asset_path: str,
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Serve static-like app asset files (css/js/json/html) from app workspace."""
    if _is_disallowed_asset_path(asset_path):
        raise HTTPException(status_code=404, detail="Asset not found")
    service = LiveAppService.create(tenant_id=current_user.tenant_id, db_session=db)
    file_payload = await service.read_file_for_actor(
        app_id=app_id,
        path=asset_path,
        actor=_actor_ctx(current_user),
        environment=environment,
    )
    return Response(
        content=file_payload["content"],
        media_type=_asset_media_type(asset_path),
        headers=_app_cache_headers(environment),
    )
