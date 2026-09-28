"""Docling parsing integration tests — no Postgres/Chroma (unlike tests/integration/)."""

from __future__ import annotations

import importlib
import os
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import docker
import pytest
from testcontainers.core.container import DockerContainer

from tests.helpers.parsing_quality import list_available_integration_sources, pinned_docling_image

DOCLING_STARTUP_TIMEOUT_SECONDS = int(os.getenv("DOCLING_STARTUP_TIMEOUT_SECONDS", "300"))
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")


def _log(message: str) -> None:
    print(f"[docling-integration] {message}", file=sys.stderr, flush=True)


def _ensure_docker_host() -> None:
    if os.environ.get("DOCKER_HOST"):
        return
    if Path("/var/run/docker.sock").exists():
        return
    for socket_path in (
        Path.home() / ".colima" / "default" / "docker.sock",
        Path.home() / ".rd" / "docker.sock",
    ):
        if socket_path.exists():
            os.environ["DOCKER_HOST"] = f"unix://{socket_path}"
            return


def _ensure_docker_daemon_available() -> None:
    try:
        client = docker.from_env()
        client.ping()
    except docker.errors.DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable: {exc}")


def _wait_for_docling_http(host: str, port: int, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    candidates = (
        f"http://{host}:{port}/health",
        f"http://{host}:{port}/docs",
    )
    started = time.time()

    while time.time() < deadline:
        for url in candidates:
            try:
                with urlopen(url, timeout=3) as response:  # noqa: S310 - controlled local test endpoint
                    if response.status == 200:
                        elapsed = int(time.time() - started)
                        _log(f"Docling ready at {host}:{port} ({elapsed}s)")
                        return
            except (URLError, TimeoutError, OSError):
                continue
        elapsed = int(time.time() - started)
        if elapsed % 10 == 0 and elapsed > 0:
            _log(f"Waiting for Docling HTTP on {host}:{port} ({elapsed}s / {timeout_seconds}s)...")
        time.sleep(2)

    raise TimeoutError(f"Docling HTTP endpoint did not become ready on {host}:{port}")


def _reload_env_config() -> None:
    import apps.config

    importlib.reload(apps.config)


@pytest.fixture(scope="session")
def docling_service_url():
    """Start pinned Docling Serve in an isolated testcontainer."""
    if not list_available_integration_sources():
        pytest.skip("no binary fixtures under tests/fixtures/parsing/sources/")

    _ensure_docker_host()
    _ensure_docker_daemon_available()
    docling_image = pinned_docling_image()
    _log(f"Starting Docling container ({docling_image}) — first pull can take 10+ minutes")
    with (
        DockerContainer(docling_image)
        .with_kwargs(platform="linux/amd64")
        .with_exposed_ports(5001)
        .with_env("DOCLING_SERVE_ENABLE_UI", "0")
    ) as container:
        host = container.get_container_host_ip()
        port = int(container.get_exposed_port(5001))
        _log(f"Container up, probing {host}:{port} (models loading, may take several minutes)")
        _wait_for_docling_http(host, port, DOCLING_STARTUP_TIMEOUT_SECONDS)
        url = f"http://{host}:{port}"
        os.environ["DOCLING_SERVICE_URL"] = url
        os.environ["DOCLING_API_KEY"] = ""
        _reload_env_config()
        yield url
        os.environ.pop("DOCLING_SERVICE_URL", None)
        _reload_env_config()
