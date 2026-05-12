from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from apps.sandbox_service.skill_packages import SkillPackageInstaller


def _write_requirements(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _docker_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except OSError:
        return False


@pytest.mark.asyncio
async def test_installer_installs_single_and_multiple_skills(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    packages_root = tmp_path / "skill-packages"

    _write_requirements(skills_root / "skill-one" / "requirements.txt", "requests==2.32.3\n")
    _write_requirements(skills_root / "skill-two" / "requirements.txt", "httpx==0.27.0\n")

    calls: list[list[str]] = []

    async def _fake_install_runner(cmd: list[str]) -> tuple[int, str]:
        calls.append(cmd)
        return 0, "ok"

    installer = SkillPackageInstaller(
        runner_image="runner",
        network_mode="bridge",
        cpu_limit="1",
        memory_limit="256m",
        pids_limit="64",
        docker_bind_src=lambda p: p,
        install_runner=_fake_install_runner,
    )

    await installer.ensure_skill_packages(str(skills_root), str(packages_root))

    assert len(calls) == 2
    assert (packages_root / "skill-one" / "python" / ".installed").exists()
    assert (packages_root / "skill-two" / "python" / ".installed").exists()


@pytest.mark.asyncio
async def test_installer_reinstalls_on_add_upgrade_downgrade_delete(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    packages_root = tmp_path / "skill-packages"
    requirements_path = skills_root / "weather-ip-helper" / "requirements.txt"
    _write_requirements(requirements_path, "requests==2.31.0\n")

    calls: list[list[str]] = []

    async def _fake_install_runner(cmd: list[str]) -> tuple[int, str]:
        calls.append(cmd)
        return 0, "ok"

    installer = SkillPackageInstaller(
        runner_image="runner",
        network_mode="bridge",
        cpu_limit="1",
        memory_limit="256m",
        pids_limit="64",
        docker_bind_src=lambda p: p,
        install_runner=_fake_install_runner,
    )

    await installer.ensure_skill_packages(str(skills_root), str(packages_root))
    assert len(calls) == 1

    # add package
    requirements_path.write_text("requests==2.31.0\nhttpx==0.27.0\n", encoding="utf-8")
    await installer.ensure_skill_packages(str(skills_root), str(packages_root))
    assert len(calls) == 2

    # upgrade package
    requirements_path.write_text("requests==2.32.3\nhttpx==0.27.0\n", encoding="utf-8")
    await installer.ensure_skill_packages(str(skills_root), str(packages_root))
    assert len(calls) == 3

    # downgrade package
    requirements_path.write_text("requests==2.30.0\nhttpx==0.27.0\n", encoding="utf-8")
    await installer.ensure_skill_packages(str(skills_root), str(packages_root))
    assert len(calls) == 4

    # delete package
    requirements_path.write_text("requests==2.30.0\n", encoding="utf-8")
    await installer.ensure_skill_packages(str(skills_root), str(packages_root))
    assert len(calls) == 5


@pytest.mark.asyncio
async def test_installer_skips_skill_without_requirements(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    packages_root = tmp_path / "skill-packages"

    (skills_root / "skill-no-req").mkdir(parents=True, exist_ok=True)
    _write_requirements(skills_root / "skill-with-req" / "requirements.txt", "requests==2.32.3\n")

    calls: list[list[str]] = []

    async def _fake_install_runner(cmd: list[str]) -> tuple[int, str]:
        calls.append(cmd)
        return 0, "ok"

    installer = SkillPackageInstaller(
        runner_image="runner",
        network_mode="bridge",
        cpu_limit="1",
        memory_limit="256m",
        pids_limit="64",
        docker_bind_src=lambda p: p,
        install_runner=_fake_install_runner,
    )

    await installer.ensure_skill_packages(str(skills_root), str(packages_root))

    assert len(calls) == 1
    assert not (packages_root / "skill-no-req").exists()
    assert (packages_root / "skill-with-req" / "python" / ".installed").exists()


@pytest.mark.skipif(not _docker_available(), reason="Docker daemon unavailable")
def test_direct_install_to_skill_packages_fails_with_readonly_mount(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    packages_root = tmp_path / "skill-packages"
    (skills_root / "demo").mkdir(parents=True, exist_ok=True)
    packages_root.mkdir(parents=True, exist_ok=True)

    cmd = [
        "docker",
        "run",
        "--rm",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,noexec,size=64m",
        "--mount",
        f"type=bind,src={skills_root},dst=/skills,readonly",
        "--mount",
        f"type=bind,src={packages_root},dst=/skill-packages,readonly",
        "python:3.11-slim",
        "/bin/bash",
        "-lc",
        "pip install --target /skill-packages/demo/python requests",
    ]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)

    assert result.returncode != 0


@pytest.mark.skipif(not _docker_available(), reason="Docker daemon unavailable")
def test_modifying_skills_files_fails_with_readonly_mount(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    packages_root = tmp_path / "skill-packages"
    skill_file = skills_root / "demo" / "SKILL.md"
    skill_file.parent.mkdir(parents=True, exist_ok=True)
    skill_file.write_text("name: demo\n", encoding="utf-8")
    packages_root.mkdir(parents=True, exist_ok=True)

    cmd = [
        "docker",
        "run",
        "--rm",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,noexec,size=64m",
        "--mount",
        f"type=bind,src={skills_root},dst=/skills,readonly",
        "--mount",
        f"type=bind,src={packages_root},dst=/skill-packages,readonly",
        "python:3.11-slim",
        "/bin/bash",
        "-lc",
        "echo hacked >> /skills/demo/SKILL.md",
    ]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)

    assert result.returncode != 0
    assert skill_file.read_text(encoding="utf-8") == "name: demo\n"
