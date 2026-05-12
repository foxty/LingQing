"""Skill package installation and cache management for sandbox runner."""

from __future__ import annotations

import asyncio
import hashlib
import os
import shlex
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Awaitable, Callable

from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class SkillPackageInstaller:
    """Install and cache skill dependencies declared in requirements.txt."""

    def __init__(
        self,
        *,
        runner_image: str,
        network_mode: str,
        cpu_limit: str,
        memory_limit: str,
        pids_limit: str,
        docker_bind_src: Callable[[str], str],
        install_runner: Callable[[list[str]], Awaitable[tuple[int, str]]] | None = None,
    ) -> None:
        self._runner_image = runner_image
        self._network_mode = network_mode
        self._cpu_limit = cpu_limit
        self._memory_limit = memory_limit
        self._pids_limit = pids_limit
        self._docker_bind_src = docker_bind_src
        self._install_runner = install_runner or self._run_install_command
        self._skill_install_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def ensure_skill_packages(self, host_skills_root_path: str, host_skill_packages_root_path: str) -> None:
        logger.info(
            "Ensuring skill package cache skills_root=%s packages_root=%s",
            host_skills_root_path,
            host_skill_packages_root_path,
        )
        await _ensure_host_dir(host_skill_packages_root_path)
        if not os.path.isdir(host_skills_root_path):
            logger.info("Skills root does not exist, skipping package ensure: %s", host_skills_root_path)
            return

        skill_dirs = [entry.path for entry in os.scandir(host_skills_root_path) if entry.is_dir(follow_symlinks=False)]
        logger.info("Discovered skill directories count=%s root=%s", len(skill_dirs), host_skills_root_path)
        for skill_dir in skill_dirs:
            skill_name = os.path.basename(skill_dir.rstrip(os.sep))
            await self.ensure_packages_for_skill(
                host_skill_dir=skill_dir,
                host_packages_dir=host_skill_packages_root_path,
                skill_name=skill_name,
            )

    async def ensure_packages_for_skill(
        self,
        host_skill_dir: str,
        host_packages_dir: str | None,
        skill_name: str,
    ) -> None:
        """Install packages for a single skill on demand.

        Unlike ensure_skill_packages() which scans an entire directory,
        this targets one specific skill directory.
        """
        if host_packages_dir is None:
            return

        requirements_path = os.path.join(host_skill_dir, "requirements.txt")
        if not os.path.isfile(requirements_path):
            return

        lock = self._skill_install_locks[skill_name]
        async with lock:
            requirements_hash = _compute_requirements_hash(requirements_path)
            skill_python_dir = os.path.join(host_packages_dir, skill_name, "python")
            stamp_path = os.path.join(skill_python_dir, ".installed")
            installed_hash = _read_stamp_hash(stamp_path)
            if installed_hash == requirements_hash:
                logger.info("Skill package cache hit skill=%s hash=%s", skill_name, requirements_hash[:12])
                return

            logger.info(
                "Installing skill dependencies skill=%s hash=%s previous_hash=%s",
                skill_name,
                requirements_hash[:12],
                installed_hash[:12] if installed_hash else "",
            )
            skill_root_dir = os.path.dirname(skill_python_dir)
            await asyncio.to_thread(os.makedirs, skill_root_dir, 0o755, True)
            temp_python_dir = await asyncio.to_thread(
                tempfile.mkdtemp,
                prefix="python-tmp-",
                dir=skill_root_dir,
            )
            exit_code, install_output = await self._run_skill_pip_install(
                host_skills_root_path=os.path.dirname(host_skill_dir),
                host_skill_packages_root_path=host_packages_dir,
                skill_name=skill_name,
                target_python_dir=temp_python_dir,
            )
            if exit_code != 0:
                await asyncio.to_thread(shutil.rmtree, temp_python_dir, True)
                logger.warning(
                    "Skill dependency install failed skill=%s exit_code=%s detail=%s",
                    skill_name,
                    exit_code,
                    _first_relevant_line(install_output),
                )
                # Keep command execution available even when one skill cannot be refreshed.
                # If a prior cache exists, it remains intact and can still be used.
                return

            await asyncio.to_thread(shutil.rmtree, skill_python_dir, True)
            await asyncio.to_thread(shutil.move, temp_python_dir, skill_python_dir)

            await asyncio.to_thread(Path(stamp_path).write_text, requirements_hash, "utf-8")
            logger.info("Skill dependencies installed skill=%s hash=%s", skill_name, requirements_hash[:12])

    async def _run_skill_pip_install(
        self,
        *,
        host_skills_root_path: str,
        host_skill_packages_root_path: str,
        skill_name: str,
        target_python_dir: str,
    ) -> tuple[int, str]:
        package_dir = f"/skill-packages/{skill_name}/{Path(target_python_dir).name}"
        requirements_in_container = f"/skills/{skill_name}/requirements.txt"
        install_cmd = (
            f"mkdir -p {shlex.quote(package_dir)} && "
            f"pip install --quiet --no-cache-dir --target {shlex.quote(package_dir)} "
            f"-r {shlex.quote(requirements_in_container)}"
        )
        cmd = [
            "docker",
            "run",
            "--rm",
            "--network",
            self._network_mode,
            "--cpus",
            self._cpu_limit,
            "--memory",
            self._memory_limit,
            "--pids-limit",
            self._pids_limit,
            "--read-only",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,noexec,size=64m",
            "--mount",
            f"type=bind,src={self._docker_bind_src(host_skills_root_path)},dst=/skills,readonly",
            "--mount",
            f"type=bind,src={self._docker_bind_src(host_skill_packages_root_path)},dst=/skill-packages",
            "-e",
            "PIP_CACHE_DIR=/tmp/pip-cache",
            "-e",
            "PIP_DISABLE_PIP_VERSION_CHECK=1",
            "--user",
            "1000:1000",
            self._runner_image,
            "/bin/bash",
            "-lc",
            install_cmd,
        ]
        return await self._install_runner(cmd)

    @staticmethod
    async def _run_install_command(cmd: list[str]) -> tuple[int, str]:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await process.communicate()
        output = (stdout_bytes + stderr_bytes).decode("utf-8", errors="replace")
        return process.returncode or 0, output


def build_skill_pythonpath_preamble() -> str:
    return """for __root in /skills /skills-tenant /workspace/skills; do
  [ -d "$__root" ] || continue
  for __sd in "$__root"/*/; do
    [ -d "$__sd" ] || continue
    __sn=$(basename "$__sd")
    for __pkg_root in /skill-packages /skill-packages-tenant; do
      if [ -d "$__pkg_root/$__sn/python" ]; then
        export PYTHONPATH="$__pkg_root/$__sn/python${PYTHONPATH:+:${PYTHONPATH}}"
        break
      fi
    done
  done
done
# Add Python SDK from workspace (lingqing_sdk package)
if [ -d "/workspace/lingqing_sdk" ]; then
  export PYTHONPATH="/workspace/lingqing_sdk${PYTHONPATH:+:${PYTHONPATH}}"
fi
unset __root __sd __sn __pkg_root
"""


def _compute_requirements_hash(requirements_path: str) -> str:
    with open(requirements_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _read_stamp_hash(stamp_path: str) -> str:
    try:
        with open(stamp_path, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def _first_relevant_line(text: str) -> str:
    lines = [(line or "").strip() for line in (text or "").splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ""

    for line in lines:
        if line.startswith("ERROR:"):
            return line
    for line in lines:
        upper = line.upper()
        if upper.startswith("WARNING") or upper.startswith("NOTICE"):
            continue
        return line
    return lines[0]


async def _ensure_host_dir(path: str) -> None:
    if os.path.islink(path):
        return
    await asyncio.to_thread(os.makedirs, path, mode=0o755, exist_ok=True)
