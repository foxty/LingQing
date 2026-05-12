"""Runtime external API execution for API connectors.

Supports multiple authentication types:
- none: No authentication
- api_key: Static API key in header
- bearer: Bearer token in Authorization header
- basic: HTTP Basic Auth
- custom: Session-based auth with automatic login flow
  * Logs in to obtain session tokens
  * Extracts tokens from response using configured paths
  * Injects tokens into request headers
  * Caches tokens to avoid repeated logins

Shared State Architecture:
    Token caching, rate limiting, and concurrency control use a module-level
    singleton (_SharedExecutionState) that persists across HTTP requests.
    This ensures state is shared even though ApiConnectorExecutionService
    instances are created per-request.

    Current: In-memory singleton (works for single-process dev)
    Future: Migrate to Redis for multi-worker/multi-pod deployments
    See: _SharedExecutionState docstring for migration guide
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from time import monotonic
from typing import Any
from urllib.parse import urljoin

import aiohttp

from apps.shared.api_connector.adapters import connector_entity_to_domain, operation_entity_to_domain
from apps.shared.api_connector.constants import (
    AUTH_TYPE_CUSTOM,
    CONNECTOR_STATUS_ACTIVE,
    OPERATION_STATUS_ACTIVE,
)
from apps.shared.api_connector.domain import ApiConnectorDomain
from apps.shared.api_connector.repository import ApiConnectorRepository, ApiOperationIndexRepository
from apps.shared.api_connector.schemas import ApiOperationCallParameters
from apps.shared.authz.delegation import allows_delegated_read
from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import ABAC_ACTION_READ, RESOURCE_TYPE_API_CONNECTOR
from apps.shared.utils.field_cipher import FieldCipher
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ApiExecutionResult:
    status_code: int
    body: Any
    headers: dict[str, str]
    elapsed_ms: float
    error: str | None = None


@dataclass
class _TokenBucketState:
    rate_per_second: float
    capacity: int
    tokens: float
    last_refill_at: float
    lock: asyncio.Lock


class _SharedExecutionState:
    """Shared state for API connector execution across all service instances.

    This singleton maintains state that must persist across HTTP requests:
    - Token cache: Avoid repeated login calls for session-based auth
    - Rate limiters: Enforce rate limits across all requests
    - Concurrency limits: Control concurrent requests per connector

    NOTE: This is an in-memory singleton that works for single-process deployments.
    For multi-worker/multi-pod deployments (Gunicorn, Kubernetes), this should be
    migrated to Redis or another distributed cache.

    TODO: Migrate to Redis for production deployments
    - Token cache: Redis with TTL (key: "connector:{id}:tokens")
    - Rate limiting: Redis Lua scripts for atomic token bucket
    - Concurrency: Redis distributed locks or RedisSemaphore
    """

    def __init__(self):
        # Token cache: connector_id -> {tokens: dict, expires_at: float}
        self._token_cache: dict[int, dict[str, Any]] = {}
        # Rate limiters: (tenant_id, connector_id) -> _TokenBucketState
        self._rate_limiters: dict[tuple[int, int], _TokenBucketState] = {}
        # Concurrency limits: (tenant_id, connector_id) -> Semaphore
        self._concurrency_limits: dict[tuple[int, int], asyncio.Semaphore] = {}
        # Lock for state modifications
        self._state_lock = asyncio.Lock()


# Module-level singleton - shared across all ApiConnectorExecutionService instances
_shared_execution_state = _SharedExecutionState()


class ApiConnectorExecutionService:
    """Execute indexed API operations with auth injection and ABAC checks.

    Handles authentication flows including automatic session management for
    custom auth types. Maintains token cache to minimize login calls.
    """

    def __init__(self, tenant_id: int, db_session):
        self.tenant_id = tenant_id
        self.db_session = db_session
        self.connector_repo = ApiConnectorRepository(db_session)
        self.operation_repo = ApiOperationIndexRepository(db_session)
        self.cipher = FieldCipher()

        # Use shared state singleton (persists across HTTP requests)
        # NOTE: For multi-worker deployments, migrate _shared_execution_state to Redis
        self._token_cache = _shared_execution_state._token_cache
        self._rate_limiters = _shared_execution_state._rate_limiters
        self._concurrency_limits = _shared_execution_state._concurrency_limits
        self._state_lock = _shared_execution_state._state_lock

    async def execute_operation_for_actor(
        self,
        *,
        operation_uid: str,
        actor: ActorContext,
        parameters: ApiOperationCallParameters | None,
    ) -> ApiExecutionResult:
        operation = await self.operation_repo.get_by_uid_and_tenant(operation_uid, self.tenant_id)
        if not operation or operation.status != OPERATION_STATUS_ACTIVE:
            raise ResourceNotFoundError(f"Api operation not found: {operation_uid}")
        return await self._execute_operation(operation, actor, parameters)

    async def execute_operation_by_id_for_actor(
        self,
        *,
        operation_id: int,
        actor: ActorContext,
        parameters: ApiOperationCallParameters | None,
        delegated_ids: list[int] | None = None,
    ) -> ApiExecutionResult:
        operation = await self.operation_repo.get_by_id_and_tenant(operation_id, self.tenant_id)
        if not operation or operation.status != OPERATION_STATUS_ACTIVE:
            raise ResourceNotFoundError(f"Api operation not found: {operation_id}")
        return await self._execute_operation(operation, actor, parameters, delegated_ids=delegated_ids)

    async def _execute_operation(
        self,
        operation,
        actor: ActorContext,
        parameters: ApiOperationCallParameters | None,
        delegated_ids: list[int] | None = None,
    ) -> ApiExecutionResult:
        operation_domain = operation_entity_to_domain(operation)

        connector = await self.connector_repo.get_by_id_and_tenant(operation.connector_id, self.tenant_id)
        if not connector or connector.status != CONNECTOR_STATUS_ACTIVE:
            raise ResourceNotFoundError(f"Api connector not found: {operation.connector_id}")
        # Convert to domain model with auto-decryption (cipher handles encrypted → decrypted)
        connector_domain = connector_entity_to_domain(connector, cipher=self.cipher)

        allowed = await allows_delegated_read(
            db_session=self.db_session,
            tenant_id=self.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=connector.id,
            resource_owner_id=connector.owner_id,
            action=ABAC_ACTION_READ,
            delegated_ids=delegated_ids,
        )
        if not allowed:
            raise ResourceNotFoundError(f"Access denied to API connector: {connector.id}")

        self._validate_base_url(connector_domain.base_url)

        start = monotonic()
        concurrency_guard: asyncio.Semaphore | None = None
        try:
            runtime_parameters = parameters or ApiOperationCallParameters()
            path = self._render_path(operation_domain.path_template, runtime_parameters.path)
            full_url = urljoin(connector_domain.base_url.rstrip("/") + "/", path.lstrip("/"))
            headers = await self._build_headers(
                connector_domain,
                runtime_parameters.header,
            )

            query = runtime_parameters.query
            body = runtime_parameters.body
            concurrency_guard = await self._acquire_concurrency_guard(connector_domain)
            await self._apply_rate_limit(connector_domain)

            status_code, response_headers, payload = await self._send_with_retry(
                connector=connector_domain,
                method=operation_domain.method,
                url=full_url,
                headers=headers,
                query=query,
                body=body,
            )
            return ApiExecutionResult(
                status_code=status_code,
                body=payload,
                headers=response_headers,
                elapsed_ms=(monotonic() - start) * 1000,
            )
        except Exception as exc:
            logger.exception("API execution failed")
            return ApiExecutionResult(
                status_code=0,
                body=None,
                headers={},
                elapsed_ms=(monotonic() - start) * 1000,
                error=str(exc),
            )
        finally:
            if concurrency_guard is not None:
                concurrency_guard.release()

    async def _send_with_retry(
        self,
        *,
        connector: ApiConnectorDomain,
        method: str,
        url: str,
        headers: dict[str, str],
        query: dict[str, Any],
        body: Any,
    ) -> tuple[int, dict[str, str], Any]:
        policy = connector.rate_policy
        max_retries = policy.max_retries
        retry_on_status = policy.retry_on_status_set()
        retry_backoff_ms = policy.retry_backoff_ms
        timeout_ms = policy.timeout_ms

        for attempt in range(max_retries + 1):
            try:
                status_code, response_headers, payload = await self._send_http_request(
                    method=method,
                    url=url,
                    headers=headers,
                    query=query,
                    body=body,
                    timeout_ms=timeout_ms,
                )
                if attempt < max_retries and status_code in retry_on_status:
                    await asyncio.sleep(self._retry_delay_seconds(retry_backoff_ms, attempt))
                    continue
                return status_code, response_headers, payload
            except Exception:
                if attempt >= max_retries:
                    raise
                await asyncio.sleep(self._retry_delay_seconds(retry_backoff_ms, attempt))

        raise ValidationError("API execution retry loop failed unexpectedly")

    async def _acquire_concurrency_guard(self, connector: ApiConnectorDomain) -> asyncio.Semaphore | None:
        max_concurrent = connector.rate_policy.max_concurrent_requests
        if max_concurrent <= 0:
            return None

        key = (connector.id, max_concurrent)
        async with self._state_lock:
            semaphore = self._concurrency_limits.get(key)
            if semaphore is None:
                semaphore = asyncio.Semaphore(max_concurrent)
                self._concurrency_limits[key] = semaphore
        await semaphore.acquire()
        return semaphore

    async def _apply_rate_limit(self, connector: ApiConnectorDomain) -> None:
        rate_per_second = connector.rate_policy.max_requests_per_second
        if rate_per_second <= 0:
            return

        capacity = connector.rate_policy.burst_size_value()
        key = (connector.id, capacity)
        async with self._state_lock:
            bucket = self._rate_limiters.get(key)
            if bucket is None:
                bucket = _TokenBucketState(
                    rate_per_second=rate_per_second,
                    capacity=capacity,
                    tokens=float(capacity),
                    last_refill_at=monotonic(),
                    lock=asyncio.Lock(),
                )
                self._rate_limiters[key] = bucket

        while True:
            async with bucket.lock:
                now = monotonic()
                elapsed = max(now - bucket.last_refill_at, 0.0)
                if elapsed > 0:
                    bucket.tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.rate_per_second)
                    bucket.last_refill_at = now

                if bucket.tokens >= 1:
                    bucket.tokens -= 1
                    return

                wait_seconds = (1 - bucket.tokens) / bucket.rate_per_second
            await asyncio.sleep(max(wait_seconds, 0.001))

    @staticmethod
    def _retry_delay_seconds(retry_backoff_ms: int, attempt: int) -> float:
        return (retry_backoff_ms * (2**attempt)) / 1000

    async def _get_or_refresh_session_tokens(
        self,
        connector: ApiConnectorDomain,
    ) -> dict[str, str]:
        """Obtain session tokens via login flow for custom auth.

        Flow:
        1. Check token cache - return cached tokens if valid
        2. Call login endpoint with credentials from extra_config
        3. Extract tokens from response using token_extraction paths
        4. Cache tokens with expiry time
        5. Return extracted tokens

        Args:
            connector: API connector domain model with already-decrypted auth_config

        Returns:
            Dictionary of extracted tokens (e.g., {"token": "...", "session_id": "..."})

        Raises:
            ValidationError: If login fails or tokens cannot be extracted
        """
        login_config = connector.get_login_config()
        if not login_config:
            return {}

        # Check cache first (tokens valid for TTL by default)
        now = monotonic()
        cached = self._token_cache.get(connector.id)
        if cached and cached.get("expires_at", 0) > now:
            logger.info(f"Using cached tokens for connector={connector.id}, expires_at={cached['expires_at']:.0f}")
            return cached["tokens"]

        # Build login URL and payload using domain methods
        login_url = urljoin(connector.base_url.rstrip("/") + "/", login_config.login_endpoint.lstrip("/"))
        login_method = login_config.login_method.upper()
        login_payload = connector.build_login_payload()

        # Determine query vs body based on method
        query_params = login_payload if login_method == "GET" else {}
        body = login_payload if login_method == "POST" else None

        # Reuse _send_http_request for consistent behavior (timeout, error handling, etc.)
        status_code, response_headers, login_response = await self._send_http_request(
            method=login_method,
            url=login_url,
            headers={"Content-Type": "application/json"},
            query=query_params,
            body=body,
        )

        if status_code != 200:
            error_msg = f"Login failed with status {status_code}"
            if isinstance(login_response, str):
                error_msg += f": {login_response[:500]}"
            raise ValidationError(error_msg)

        logger.debug(f"Login response received, status: {status_code}, response preview: {str(login_response)[:500]}")

        # Extract tokens using domain method
        tokens = connector.extract_tokens_from_response(login_response)

        # Cache tokens with expiry
        expires_at = now + login_config.token_ttl_seconds
        self._token_cache[connector.id] = {"tokens": tokens, "expires_at": expires_at}

        logger.info(
            f"Session tokens obtained and cached for connector={connector.id}, now={now}, expires_at={expires_at}"
        )
        return tokens

    async def _send_http_request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        query: dict[str, Any],
        body: Any,
        timeout_ms: int = 10_000,
    ) -> tuple[int, dict[str, str], Any]:
        timeout = aiohttp.ClientTimeout(total=max(timeout_ms, 1) / 1000)
        logger.info(f"Sending {method} request to {url}")
        logger.debug(f"With headers={headers} and body={body}")
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(method=method, url=url, headers=headers, params=query, json=body) as response:
                text = await response.text()
                payload: Any
                try:
                    payload = await response.json(content_type=None)
                except Exception:
                    payload = text
                return response.status, dict(response.headers), payload

    async def _build_headers(
        self,
        connector: ApiConnectorDomain,
        extra_headers: dict[str, Any],
    ) -> dict[str, str]:
        """Build HTTP headers for API request based on authentication type.

        For custom auth (AUTH_TYPE_CUSTOM) with login flow:
        - Performs automatic login to get tokens
        - Extracts tokens from login response
        - Substitutes placeholders in request_headers with actual token values
        - Caches tokens to avoid repeated logins

        For other auth types (api_key, bearer, basic, none):
        - Delegates to domain model's build_headers() method

        Args:
            connector: API connector domain model with already-decrypted auth_config
            extra_headers: Additional headers from operation call parameters

        Returns:
            Dictionary of HTTP headers to include in API request
        """
        # Get auth_config from domain model (already decrypted)
        auth_config = connector.auth_config
        headers = {"User-Agent": "LingQing-ApiConnector/1.0"}
        headers.update({str(k): str(v) for k, v in (extra_headers or {}).items()})

        # Handle custom auth with login flow (dynamic token substitution)
        if connector.auth_type == AUTH_TYPE_CUSTOM and auth_config.login_endpoint:
            # Perform login to obtain session tokens
            tokens = await self._get_or_refresh_session_tokens(connector)

            # Build headers with token substitution using domain method
            headers.update(connector.build_custom_headers_with_tokens(tokens))
            return headers

        # For all other auth types, delegate to domain model
        return connector.build_headers(extra_headers)

    @staticmethod
    def _render_path(path_template: str, path_params: dict[str, Any]) -> str:
        rendered = path_template
        for key, value in (path_params or {}).items():
            rendered = rendered.replace("{" + key + "}", str(value))
        if "{" in rendered or "}" in rendered:
            raise ValidationError("Missing required path parameters")
        return rendered

    @staticmethod
    def _validate_base_url(base_url: str) -> None:
        from urllib.parse import urlparse

        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValidationError("Only http/https base_url is supported")
        host = parsed.hostname
        if not host:
            raise ValidationError("Invalid base_url")

        try:
            resolved_ip = ipaddress.ip_address(host)
        except ValueError:
            try:
                resolved_ip = ipaddress.ip_address(socket.gethostbyname(host))
            except Exception as exc:
                raise ValidationError(f"Failed to resolve base_url host: {host}") from exc

        if resolved_ip.is_loopback or resolved_ip.is_link_local:
            raise ValidationError("base_url resolves to loopback address")
