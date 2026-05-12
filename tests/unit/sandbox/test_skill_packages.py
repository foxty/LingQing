import asyncio
import hashlib
from pathlib import Path

import pytest

from apps.sandbox_service.skill_packages import SkillPackageInstaller


def _write_requirements(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.mark.asyncio
async def test_ensure_skill_packages_installs_and_writes_stamp(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    packages_root = tmp_path / "skill-packages"
    requirements_path = skills_root / "weather-ip-helper" / "requirements.txt"
    _write_requirements(requirements_path, "requests==2.32.3\n")

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
    stamp_path = packages_root / "weather-ip-helper" / "python" / ".installed"
    assert stamp_path.exists()
    expected_hash = hashlib.sha256(requirements_path.read_bytes()).hexdigest()
    assert stamp_path.read_text(encoding="utf-8") == expected_hash


@pytest.mark.asyncio
async def test_ensure_skill_packages_skips_when_hash_unchanged(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    packages_root = tmp_path / "skill-packages"
    requirements_path = skills_root / "weather-ip-helper" / "requirements.txt"
    _write_requirements(requirements_path, "requests==2.32.3\n")

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
    await installer.ensure_skill_packages(str(skills_root), str(packages_root))

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_ensure_skill_packages_reinstalls_and_cleans_on_hash_change(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    packages_root = tmp_path / "skill-packages"
    requirements_path = skills_root / "weather-ip-helper" / "requirements.txt"
    _write_requirements(requirements_path, "requests==2.32.3\n")

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

    stale_file = packages_root / "weather-ip-helper" / "python" / "stale.txt"
    stale_file.write_text("old", encoding="utf-8")
    requirements_path.write_text("requests==2.31.0\n", encoding="utf-8")

    await installer.ensure_skill_packages(str(skills_root), str(packages_root))

    assert len(calls) == 2
    assert not stale_file.exists()
    expected_hash = hashlib.sha256(requirements_path.read_bytes()).hexdigest()
    stamp_path = packages_root / "weather-ip-helper" / "python" / ".installed"
    assert stamp_path.read_text(encoding="utf-8") == expected_hash


@pytest.mark.asyncio
async def test_ensure_skill_packages_continues_on_install_failure(tmp_path: Path) -> None:
    """Test that installation continues when a skill fails (graceful degradation).

    Design: When one skill installation fails, the system should:
    1. Log a warning
    2. Continue processing other skills
    3. Not raise an exception (allow partial success)

    This is intentional so that a single failing skill doesn't block all others.
    """
    skills_root = tmp_path / "skills"
    packages_root = tmp_path / "skill-packages"

    # Create two skills: one will fail, one will succeed
    requirements_path_1 = skills_root / "failing-skill" / "requirements.txt"
    requirements_path_2 = skills_root / "working-skill" / "requirements.txt"
    _write_requirements(requirements_path_1, "requests==2.32.3\n")
    _write_requirements(requirements_path_2, "httpx==0.27.0\n")

    calls: list[list[str]] = []

    async def _selective_fail_runner(cmd: list[str]) -> tuple[int, str]:
        # Fail the first skill, succeed on the second
        if "failing-skill" in str(cmd):
            return 1, "boom\nstack"
        calls.append(cmd)
        return 0, "ok"

    installer = SkillPackageInstaller(
        runner_image="runner",
        network_mode="bridge",
        cpu_limit="1",
        memory_limit="256m",
        pids_limit="64",
        docker_bind_src=lambda p: p,
        install_runner=_selective_fail_runner,
    )

    # Should NOT raise - continues on failure
    await installer.ensure_skill_packages(str(skills_root), str(packages_root))

    # Verify: working skill was installed (1 call)
    assert len(calls) == 1
    # Verify: failing skill has no stamp file
    failing_stamp = packages_root / "failing-skill" / "python" / ".installed"
    assert not failing_stamp.exists()
    # Verify: working skill has stamp file
    working_stamp = packages_root / "working-skill" / "python" / ".installed"
    assert working_stamp.exists()


@pytest.mark.asyncio
async def test_concurrent_installs_for_same_skill_use_lock(tmp_path: Path) -> None:
    """Verify that concurrent installs for the same skill are serialized."""
    skills_root = tmp_path / "skills"
    packages_root = tmp_path / "skill-packages"
    requirements_path = skills_root / "concurrent-skill" / "requirements.txt"
    _write_requirements(requirements_path, "requests==2.32.3\n")

    call_count = 0
    install_started = asyncio.Event()
    install_can_finish = asyncio.Event()

    async def _slow_install_runner(cmd: list[str]) -> tuple[int, str]:
        nonlocal call_count
        call_count += 1
        install_started.set()
        await install_can_finish.wait()
        return 0, "ok"

    installer = SkillPackageInstaller(
        runner_image="runner",
        network_mode="bridge",
        cpu_limit="1",
        memory_limit="256m",
        pids_limit="64",
        docker_bind_src=lambda p: p,
        install_runner=_slow_install_runner,
    )

    # Start two concurrent installs for the same skill
    task1 = asyncio.create_task(
        installer.ensure_packages_for_skill(
            host_skill_dir=str(skills_root / "concurrent-skill"),
            host_packages_dir=str(packages_root),
            skill_name="concurrent-skill",
        )
    )
    task2 = asyncio.create_task(
        installer.ensure_packages_for_skill(
            host_skill_dir=str(skills_root / "concurrent-skill"),
            host_packages_dir=str(packages_root),
            skill_name="concurrent-skill",
        )
    )

    # Wait for first install to start
    await install_started.wait()

    # Allow it to finish
    install_can_finish.set()

    # Both should complete
    await asyncio.gather(task1, task2)

    # Only one actual install should have occurred due to locking
    assert call_count == 1


@pytest.mark.asyncio
async def test_temp_dir_cleanup_on_failure(tmp_path: Path) -> None:
    """Verify temporary directories are cleaned up when install fails."""
    skills_root = tmp_path / "skills"
    packages_root = tmp_path / "skill-packages"
    requirements_path = skills_root / "failing-skill" / "requirements.txt"
    _write_requirements(requirements_path, "invalid-package==999.999.999\n")

    async def _fail_runner(cmd: list[str]) -> tuple[int, str]:
        return 1, "ERROR: Could not find version"

    installer = SkillPackageInstaller(
        runner_image="runner",
        network_mode="bridge",
        cpu_limit="1",
        memory_limit="256m",
        pids_limit="64",
        docker_bind_src=lambda p: p,
        install_runner=_fail_runner,
    )

    await installer.ensure_packages_for_skill(
        host_skill_dir=str(skills_root / "failing-skill"),
        host_packages_dir=str(packages_root),
        skill_name="failing-skill",
    )

    # Verify no temp directories remain
    skill_root = packages_root / "failing-skill"
    if skill_root.exists():
        temp_dirs = [d for d in skill_root.iterdir() if d.name.startswith("python-tmp-")]
        assert len(temp_dirs) == 0, f"Found leftover temp dirs: {temp_dirs}"


@pytest.mark.asyncio
async def test_ensure_host_dir_handles_symlink(tmp_path: Path) -> None:
    """Test that _ensure_host_dir skips symlinks."""
    from apps.sandbox_service.skill_packages import _ensure_host_dir

    target_dir = tmp_path / "target"
    target_dir.mkdir()
    symlink_path = tmp_path / "symlink"
    symlink_path.symlink_to(target_dir)

    # Should not raise or modify symlink
    await _ensure_host_dir(str(symlink_path))
    assert symlink_path.is_symlink()
    assert symlink_path.resolve() == target_dir.resolve()
