"""Unit tests for live app workspace utilities."""

from pathlib import Path

import pytest

from apps.shared.live_app.workspace import (
    ALLOWED_APP_FILE_SUFFIXES,
    LiveAppWriteLockTimeoutError,
    app_write_lock,
    commit_app_changes,
    ensure_entry_file,
    get_app_path,
    grep_app_files,
    has_uncommitted_changes,
    init_app_repo,
    list_app_files,
    read_app_file,
    read_entry,
    write_app_file,
)


def test_ensure_read_write_entry_roundtrip(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_apps_root",
        lambda tenant_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps"),
    )
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_app_path",
        lambda tenant_id, app_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps" / f"app_{app_id}"),
    )

    entry_path = ensure_entry_file(tenant_id=11, app_id=101)
    assert entry_path.exists()

    write_app_file(tenant_id=11, app_id=101, relative_path="entry.html", content="<html>ok</html>")
    content = read_entry(tenant_id=11, app_id=101)
    assert content == "<html>ok</html>"


def test_get_app_path_create(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_apps_root",
        lambda tenant_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps"),
    )
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_app_path",
        lambda tenant_id, app_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps" / f"app_{app_id}"),
    )

    app_path = get_app_path(tenant_id=22, app_id=202, create=True)
    assert app_path.exists()
    assert app_path == tmp_path / "tenants" / "tenant_22" / "apps" / "app_202" / "env" / "prod"


def test_ensure_entry_file_bootstrap_template(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_apps_root",
        lambda tenant_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps"),
    )
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_app_path",
        lambda tenant_id, app_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps" / f"app_{app_id}"),
    )

    entry_path = ensure_entry_file(tenant_id=23, app_id=203)
    content = entry_path.read_text(encoding="utf-8")
    assert "window.LQ.liveApp.query" in content
    assert "Live App ready." in content


def test_entry_path_traversal_guard(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_apps_root",
        lambda tenant_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps"),
    )
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_app_path",
        lambda tenant_id, app_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps" / f"app_{app_id}"),
    )

    with pytest.raises(ValueError):
        ensure_entry_file(tenant_id=33, app_id=303, entry_file="../../escape.html")


def test_init_app_repo_idempotent(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_apps_root",
        lambda tenant_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps"),
    )
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_app_path",
        lambda tenant_id, app_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps" / f"app_{app_id}"),
    )

    calls = {"count": 0}

    def _fake_run(*args, **kwargs):
        calls["count"] += 1
        git_dir = tmp_path / "tenants" / "tenant_44" / "apps" / "app_404" / ".git"
        git_dir.mkdir(parents=True, exist_ok=True)

        class _Result:
            returncode = 0

        return _Result()

    monkeypatch.setattr("apps.shared.live_app.workspace.subprocess.run", _fake_run)

    init_app_repo(tenant_id=44, app_id=404)
    init_app_repo(tenant_id=44, app_id=404)
    assert calls["count"] == 1


def test_write_app_file_respects_per_app_lock(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_apps_root",
        lambda tenant_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps"),
    )
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_app_path",
        lambda tenant_id, app_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps" / f"app_{app_id}"),
    )

    ensure_entry_file(tenant_id=55, app_id=505)

    with app_write_lock(tenant_id=55, app_id=505, timeout_seconds=0.1):
        with pytest.raises(LiveAppWriteLockTimeoutError):
            write_app_file(
                tenant_id=55,
                app_id=505,
                relative_path="entry.html",
                content="<html>blocked</html>",
                lock_timeout_seconds=0.01,
            )


def test_read_write_list_app_files(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_apps_root",
        lambda tenant_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps"),
    )
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_app_path",
        lambda tenant_id, app_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps" / f"app_{app_id}"),
    )

    write_app_file(tenant_id=77, app_id=707, relative_path="src/components/table.js", content="export const t = 1;")
    content = read_app_file(tenant_id=77, app_id=707, relative_path="src/components/table.js")
    assert content == "export const t = 1;"
    files = list_app_files(tenant_id=77, app_id=707)
    assert "src/components/table.js" in files

    grep_result = grep_app_files(tenant_id=77, app_id=707, pattern=r"export\s+const")
    assert grep_result["truncated"] is False
    assert len(grep_result["matches"]) == 1
    assert grep_result["matches"][0]["path"] == "src/components/table.js"


def test_grep_app_files_rejects_empty_or_invalid_pattern():
    with pytest.raises(ValueError, match="pattern must not be empty"):
        grep_app_files(tenant_id=1, app_id=1, pattern="  ")
    with pytest.raises(ValueError, match="Invalid regex"):
        grep_app_files(tenant_id=1, app_id=1, pattern="(")


def test_write_app_file_rejects_invalid_suffix(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_apps_root",
        lambda tenant_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps"),
    )
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_app_path",
        lambda tenant_id, app_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps" / f"app_{app_id}"),
    )

    with pytest.raises(ValueError):
        write_app_file(tenant_id=78, app_id=708, relative_path="notes.asp", content="bad")

    assert ".asp" not in ALLOWED_APP_FILE_SUFFIXES


def test_git_repo_is_scoped_per_app(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_apps_root",
        lambda tenant_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps"),
    )
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_app_path",
        lambda tenant_id, app_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps" / f"app_{app_id}"),
    )
    calls = {"count": 0}

    def _fake_run(*args, **kwargs):
        calls["count"] += 1
        repo_path = tmp_path / "tenants" / "tenant_99" / "apps" / "app_1001"
        (repo_path / ".git").mkdir(parents=True, exist_ok=True)

        class _Result:
            returncode = 0

        return _Result()

    monkeypatch.setattr("apps.shared.live_app.workspace.subprocess.run", _fake_run)
    init_app_repo(tenant_id=99, app_id=1001)
    assert (tmp_path / "tenants" / "tenant_99" / "apps" / "app_1001" / ".git").exists()
    assert calls["count"] == 1


def test_has_uncommitted_changes_clean_after_commit(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_apps_root",
        lambda tenant_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps"),
    )
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_app_path",
        lambda tenant_id, app_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps" / f"app_{app_id}"),
    )

    init_app_repo(tenant_id=88, app_id=808)
    write_app_file(tenant_id=88, app_id=808, relative_path="src/main.js", content="v1")
    commit_app_changes(tenant_id=88, app_id=808, commit_message="initial")

    assert not has_uncommitted_changes(tenant_id=88, app_id=808)

    write_app_file(tenant_id=88, app_id=808, relative_path="src/main.js", content="v2")
    assert has_uncommitted_changes(tenant_id=88, app_id=808)

    commit_app_changes(tenant_id=88, app_id=808, commit_message="update")
    assert not has_uncommitted_changes(tenant_id=88, app_id=808)
