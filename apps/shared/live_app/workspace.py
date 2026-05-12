"""Workspace utilities for live app runtime files."""

import os
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Sequence

from apps.config import get_tenant_live_app_path, get_tenant_live_apps_root
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_ENTRY_FILE = "entry.html"
DEFAULT_WRITE_LOCK_TIMEOUT_SECONDS = 2.0
ALLOWED_APP_FILE_SUFFIXES = {".html", ".js", ".css", ".json", ".sql", ".md", ".py", ".txt"}
DEFAULT_LIVE_APP_ENVIRONMENT = "prod"
ALLOWED_LIVE_APP_ENVIRONMENTS = {"dev", "test", "prod"}
_DEFAULT_GREP_MAX_MATCHES = 100
_MAX_GREP_MAX_MATCHES = 500
_DEFAULT_GREP_MAX_FILE_BYTES = 512_000
_MAX_GREP_LINE_CHARS = 500
DEFAULT_ENTRY_HTML = """<!doctype html>
<html>
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Live App</title>
  </head>
  <body>
    <div id="app">Live App ready.</div>
    <script>
      async function bootLiveApp() {
        if (!window.LQ || !window.LQ.liveApp) return;
        try {
          await window.LQ.liveApp.query("SELECT 1 as ok");
        } catch (_err) {
          // Keep default template resilient when runtime data path is not configured yet.
        }
      }
      bootLiveApp();
    </script>
  </body>
</html>
"""

_APP_LOCKS: dict[tuple[int, int, str], threading.Lock] = {}
_APP_LOCKS_GUARD = threading.Lock()


class LiveAppWriteLockTimeoutError(RuntimeError):
    """Raised when write lock cannot be acquired within timeout."""

    pass


def _normalize_environment(environment: str) -> str:
    normalized = (environment or "").strip().lower()
    if normalized not in ALLOWED_LIVE_APP_ENVIRONMENTS:
        raise ValueError(f"Invalid environment '{environment}'. Allowed: {sorted(ALLOWED_LIVE_APP_ENVIRONMENTS)}")
    return normalized


def _get_app_lock(tenant_id: int, app_id: int, environment: str) -> threading.Lock:
    normalized_env = _normalize_environment(environment)
    lock_key = (tenant_id, app_id, normalized_env)
    with _APP_LOCKS_GUARD:
        if lock_key not in _APP_LOCKS:
            _APP_LOCKS[lock_key] = threading.Lock()
        return _APP_LOCKS[lock_key]


@contextmanager
def app_write_lock(
    tenant_id: int,
    app_id: int,
    *,
    environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    timeout_seconds: float = DEFAULT_WRITE_LOCK_TIMEOUT_SECONDS,
):
    """Acquire per-app write lock with timeout and always release."""
    normalized_env = _normalize_environment(environment)
    lock = _get_app_lock(tenant_id, app_id, normalized_env)
    acquired = lock.acquire(timeout=timeout_seconds)
    if not acquired:
        raise LiveAppWriteLockTimeoutError(
            f"Could not acquire live app write lock for tenant={tenant_id}, app={app_id} within {timeout_seconds}s"
        )
    try:
        yield
    finally:
        lock.release()


def get_app_repo_path(tenant_id: int, app_id: int) -> Path:
    """Return app-scoped git repository path (config-managed)."""
    return Path(get_tenant_live_app_path(tenant_id, app_id))


_DEFAULT_GITIGNORE = """\
.DS_Store
Thumbs.db
__pycache__/
*.pyc
.env
"""


def _git_cli_prefix(repo_path: Path) -> list[str]:
    """Git 2.35+ rejects repos not owned by the current user; data dirs are often bind-mounted with mixed ownership."""
    resolved = str(repo_path.resolve())
    return ["git", "-c", f"safe.directory={resolved}"]


def init_app_repo(tenant_id: int, app_id: int) -> Path:
    """Initialize app-scoped git repository if not exists."""
    app_repo = get_app_repo_path(tenant_id, app_id)
    app_repo.mkdir(parents=True, exist_ok=True)

    git_dir = app_repo / ".git"
    if git_dir.exists():
        return app_repo

    subprocess.run(
        _git_cli_prefix(app_repo) + ["init"],
        cwd=str(app_repo),
        check=True,
        capture_output=True,
        text=True,
    )
    gitignore_path = app_repo / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(_DEFAULT_GITIGNORE, encoding="utf-8")
    logger.info("Initialized live app workspace git repo for tenant=%s app=%s at %s", tenant_id, app_id, app_repo)
    return app_repo


def _require_app_repo(tenant_id: int, app_id: int) -> Path:
    """Return app repo path and require git initialization."""
    app_repo = get_app_repo_path(tenant_id, app_id)
    git_dir = app_repo / ".git"
    if not git_dir.exists():
        raise RuntimeError(
            f"App live app git repo is not initialized for tenant={tenant_id} app_id={app_id}. "
            "Initialize it during live app creation/bootstrap."
        )
    return app_repo


def get_app_path(
    tenant_id: int,
    app_id: int,
    *,
    environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    create: bool = False,
) -> Path:
    """Return app path in tenant workspace."""
    normalized_env = _normalize_environment(environment)
    app_root = (
        Path(get_tenant_live_app_path(tenant_id, app_id))
        if create
        else Path(get_tenant_live_apps_root(tenant_id)) / f"app_{app_id}"
    )
    app_path = app_root / "env" / normalized_env

    if create:
        app_path.mkdir(parents=True, exist_ok=True)
    return app_path


def _resolve_entry_path(app_path: Path, entry_file: str) -> Path:
    entry_path = _resolve_app_relative_path(app_path, entry_file)
    return entry_path


def _resolve_app_relative_path(app_path: Path, relative_path: str) -> Path:
    rel_path = Path(relative_path)
    if rel_path.is_absolute():
        raise ValueError(f"Path '{relative_path}' must be relative to app root")
    entry_path = (app_path / rel_path).resolve()
    app_root = app_path.resolve()
    if not str(entry_path).startswith(str(app_root)):
        raise ValueError(f"Path '{relative_path}' is outside app workspace")
    return entry_path


def _validate_app_file_suffix(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix not in ALLOWED_APP_FILE_SUFFIXES:
        raise ValueError(f"File suffix '{suffix}' is not allowed. Allowed: {sorted(ALLOWED_APP_FILE_SUFFIXES)}")


def _validate_job_path(relative_path: str) -> None:
    """Ensure job files are under jobs/ directory with .py extension.

    Args:
        relative_path: Relative path within app workspace (e.g., 'jobs/sync_api.py')

    Raises:
        ValueError: If path is not under jobs/ or doesn't have .py extension
    """
    if not relative_path.startswith("jobs/"):
        raise ValueError(f"Job files must be under 'jobs/' directory: {relative_path}")
    if not relative_path.endswith(".py"):
        raise ValueError(f"Job files must have .py extension: {relative_path}")


def _bootstrap_python_sdk(app_path: Path) -> None:
    """Copy Python SDK to app workspace for sandbox execution.

    The SDK is copied to <app_path>/lingqing_sdk/ so that job scripts
    can import it via: from lingqing_sdk import LiveAppClient

    Args:
        app_path: App environment directory path
    """
    # Source: apps/shared/sdk/py-api/
    # We need to navigate from workspace.py location to py-api
    # workspace.py is in apps/shared/live_app/
    # py-api is in apps/shared/sdk/py-api/
    current_file = Path(__file__).resolve()
    sdk_source = current_file.parents[1] / "sdk" / "py-api"

    if not sdk_source.exists():
        logger.warning("Python SDK source not found at %s, skipping SDK bootstrap", sdk_source)
        return

    sdk_dest = app_path / "lingqing_sdk"

    # Only copy if not already present (avoid overwriting on subsequent boots)
    if sdk_dest.exists():
        logger.debug("Python SDK already exists at %s, skipping copy", sdk_dest)
    else:
        shutil.copytree(sdk_source, sdk_dest)
        logger.info("Copied Python SDK to %s", sdk_dest)


def ensure_entry_file(
    tenant_id: int,
    app_id: int,
    entry_file: str = DEFAULT_ENTRY_FILE,
    *,
    environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
) -> Path:
    """Ensure entry file exists and return its path."""
    app_path = get_app_path(tenant_id, app_id, environment=environment, create=True)
    entry_path = _resolve_entry_path(app_path, entry_file)
    if not entry_path.exists():
        entry_path.write_text(DEFAULT_ENTRY_HTML, encoding="utf-8")

    # Bootstrap Python SDK for sandbox job execution
    _bootstrap_python_sdk(app_path)

    return entry_path


def read_entry(
    tenant_id: int,
    app_id: int,
    entry_file: str = DEFAULT_ENTRY_FILE,
    *,
    environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
) -> str:
    """Read entry file content."""
    app_path = get_app_path(tenant_id, app_id, environment=environment, create=False)
    entry_path = _resolve_entry_path(app_path, entry_file)
    return entry_path.read_text(encoding="utf-8")


def list_app_files(
    tenant_id: int,
    app_id: int,
    *,
    environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
) -> list[str]:
    """List app files relative to app root."""
    app_path = get_app_path(tenant_id, app_id, environment=environment, create=True)
    files: list[str] = []
    for path in app_path.rglob("*"):
        if path.is_file():
            files.append(path.relative_to(app_path).as_posix())
    files.sort()
    return files


def grep_app_files(
    tenant_id: int,
    app_id: int,
    pattern: str,
    *,
    environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    case_insensitive: bool = False,
    max_matches: int = _DEFAULT_GREP_MAX_MATCHES,
    max_file_bytes: int = _DEFAULT_GREP_MAX_FILE_BYTES,
) -> dict[str, Any]:
    """Search file contents under the app workspace using a Python regex pattern.

    Only scans files with allowed app suffixes (same as read). Skips files larger than
    ``max_file_bytes``. Returns at most ``max_matches`` hits (``truncated`` if cut off).
    """
    raw = (pattern or "").strip()
    if not raw:
        raise ValueError("pattern must not be empty")
    normalized_env = _normalize_environment(environment)

    capped = min(max(1, int(max_matches)), _MAX_GREP_MAX_MATCHES)
    try:
        rx = re.compile(raw, flags=re.IGNORECASE if case_insensitive else 0)
    except re.error as e:
        raise ValueError(f"Invalid regex: {e}") from e

    app_path = get_app_path(tenant_id, app_id, environment=normalized_env, create=True)
    files = list_app_files(tenant_id, app_id, environment=normalized_env)
    matches: list[dict[str, Any]] = []
    truncated = False

    for rel in sorted(files):
        if truncated:
            break
        fp = _resolve_app_relative_path(app_path, rel)
        try:
            _validate_app_file_suffix(fp)
        except ValueError:
            continue
        try:
            st = fp.stat()
        except OSError:
            continue
        if st.st_size > max_file_bytes:
            continue
        try:
            text = fp.read_text(encoding="utf-8")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if rx.search(line):
                line_out = line if len(line) <= _MAX_GREP_LINE_CHARS else line[:_MAX_GREP_LINE_CHARS] + "…"
                matches.append({"path": rel, "line": line_no, "text": line_out})
                if len(matches) >= capped:
                    truncated = True
                    break
        if truncated:
            break

    return {
        "environment": normalized_env,
        "pattern": raw,
        "matches": matches,
        "truncated": truncated,
    }


def read_app_file(
    tenant_id: int,
    app_id: int,
    relative_path: str,
    *,
    environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
) -> str:
    """Read app file content by relative path."""
    app_path = get_app_path(tenant_id, app_id, environment=environment, create=False)
    file_path = _resolve_app_relative_path(app_path, relative_path)
    _validate_app_file_suffix(file_path)
    return file_path.read_text(encoding="utf-8")


def write_app_file(
    tenant_id: int,
    app_id: int,
    relative_path: str,
    content: str,
    *,
    environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    lock_timeout_seconds: float = DEFAULT_WRITE_LOCK_TIMEOUT_SECONDS,
    validate_suffix: bool = True,
) -> Path:
    """Write app file content by relative path with lock and guardrails."""
    with app_write_lock(tenant_id, app_id, environment=environment, timeout_seconds=lock_timeout_seconds):
        app_path = get_app_path(tenant_id, app_id, environment=environment, create=True)
        file_path = _resolve_app_relative_path(app_path, relative_path)
        if validate_suffix:
            _validate_app_file_suffix(file_path)
        # Additional validation for job files
        if relative_path.startswith("jobs/"):
            _validate_job_path(relative_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = file_path.with_suffix(file_path.suffix + ".tmp")
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(file_path)
        return file_path


def delete_app_file(
    tenant_id: int,
    app_id: int,
    relative_path: str,
    *,
    environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    lock_timeout_seconds: float = DEFAULT_WRITE_LOCK_TIMEOUT_SECONDS,
    validate_suffix: bool = True,
) -> bool:
    """Delete one app file by relative path with lock and guardrails."""
    with app_write_lock(tenant_id, app_id, environment=environment, timeout_seconds=lock_timeout_seconds):
        app_path = get_app_path(tenant_id, app_id, environment=environment, create=True)
        file_path = _resolve_app_relative_path(app_path, relative_path)
        if validate_suffix:
            _validate_app_file_suffix(file_path)
        # Additional validation for job files
        if relative_path.startswith("jobs/"):
            _validate_job_path(relative_path)
        if not file_path.exists():
            return False
        if not file_path.is_file():
            raise ValueError(f"Path '{relative_path}' is not a file")
        file_path.unlink()
        return True


def sync_environment_from_commit(
    tenant_id: int,
    app_id: int,
    *,
    source_environment: str,
    target_environment: str,
    commit_sha: str,
    lock_timeout_seconds: float = DEFAULT_WRITE_LOCK_TIMEOUT_SECONDS,
) -> str:
    """Replace target env with source env tree at a commit, then commit the result.

    On failure, restores the target env to its previous committed state.
    Returns the new commit SHA on the target environment.
    """
    with app_write_lock(tenant_id, app_id, environment=target_environment, timeout_seconds=lock_timeout_seconds):
        repo_path = _require_app_repo(tenant_id, app_id)
        source_root = get_app_path(tenant_id, app_id, environment=source_environment, create=True)
        source_prefix = source_root.relative_to(repo_path).as_posix()
        target_root = get_app_path(tenant_id, app_id, environment=target_environment, create=True)
        target_pathspec = target_root.relative_to(repo_path).as_posix()

        rollback_result = _run_git(repo_path, ["rev-parse", "HEAD"], check=False)
        rollback_sha = rollback_result.stdout.strip() if rollback_result.returncode == 0 else None

        try:
            _sync_and_commit(
                repo_path=repo_path,
                source_prefix=source_prefix,
                target_root=target_root,
                target_pathspec=target_pathspec,
                commit_sha=commit_sha,
                commit_message=f"Promote {source_environment}@{commit_sha[:12]} to {target_environment}",
            )
        except Exception:
            _rollback_target(repo_path, target_pathspec, rollback_sha)
            raise

        head = _run_git(repo_path, ["rev-parse", "HEAD"], check=True)
        return head.stdout.strip()


def _sync_and_commit(
    *,
    repo_path: Path,
    source_prefix: str,
    target_root: Path,
    target_pathspec: str,
    commit_sha: str,
    commit_message: str,
) -> None:
    for child in target_root.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    with tempfile.NamedTemporaryFile(suffix=".tar", delete=True) as tmp:
        archive_result = subprocess.run(
            _git_cli_prefix(repo_path) + ["archive", "--format=tar", "-o", tmp.name, commit_sha, "--", source_prefix],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if archive_result.returncode != 0:
            raise RuntimeError(f"git archive failed: {archive_result.stderr.strip()}")

        strip_components = len(source_prefix.split("/"))
        tar_result = subprocess.run(
            ["tar", "xf", tmp.name, f"--strip-components={strip_components}"],
            cwd=str(target_root),
            capture_output=True,
            text=True,
        )
        if tar_result.returncode != 0:
            raise RuntimeError(f"tar extract failed: {tar_result.stderr.strip()}")

    _run_git(repo_path, ["add", "-A", "--", target_pathspec], check=True)
    staged = _run_git(repo_path, ["diff", "--cached", "--quiet", "--", target_pathspec], check=False)
    if staged.returncode == 0:
        return
    _run_git(repo_path, ["commit", "-m", commit_message, "--", target_pathspec], check=True)


def _rollback_target(repo_path: Path, target_pathspec: str, rollback_sha: str | None) -> None:
    try:
        _run_git(repo_path, ["reset", "HEAD", "--", target_pathspec], check=False)
        if rollback_sha:
            _run_git(repo_path, ["checkout", rollback_sha, "--", target_pathspec], check=False)
        else:
            _run_git(repo_path, ["rm", "-rf", "--cached", "--", target_pathspec], check=False)
    except Exception:
        logger.exception("Failed to rollback target env %s after promotion error", target_pathspec)


def _format_git_process_failure(repo_path: Path, argv: list[str], result: subprocess.CompletedProcess) -> str:
    stderr = (result.stderr or "").strip()
    stdout = (result.stdout or "").strip()
    lines = [
        f"git failed with exit {result.returncode}",
        f"cwd: {repo_path}",
        f"cmd: {shlex.join(argv)}",
    ]
    if stderr:
        lines.append(f"stderr:\n{stderr}")
    if stdout:
        lines.append(f"stdout:\n{stdout}")
    return "\n".join(lines)


def _run_git(repo_path: Path, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Live App Agent",
        "GIT_AUTHOR_EMAIL": "live-app-agent@platform.local",
        "GIT_COMMITTER_NAME": "Live App Agent",
        "GIT_COMMITTER_EMAIL": "live-app-agent@platform.local",
    }
    argv = _git_cli_prefix(repo_path) + args
    result = subprocess.run(
        argv,
        cwd=str(repo_path),
        capture_output=True,
        text=True,
        env=env,
    )
    if check and result.returncode != 0:
        raise RuntimeError(_format_git_process_failure(repo_path, argv, result))
    return result


def commit_app_files(
    tenant_id: int,
    app_id: int,
    *,
    environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    relative_paths: Sequence[str],
    commit_message: str,
) -> bool:
    """Stage and commit app files; returns True when commit created."""
    repo_path = _require_app_repo(tenant_id, app_id)
    app_root = get_app_path(tenant_id, app_id, environment=environment, create=True)

    pathspecs: list[str] = []
    for rel in relative_paths:
        abs_path = _resolve_app_relative_path(app_root, rel)
        pathspecs.append(abs_path.relative_to(repo_path).as_posix())

    _run_git(repo_path, ["add", "--", *pathspecs], check=True)

    staged_check = _run_git(repo_path, ["diff", "--cached", "--quiet", "--", *pathspecs], check=False)
    if staged_check.returncode == 0:
        return False
    if staged_check.returncode not in (0, 1):
        raise RuntimeError(f"git diff --cached failed: {staged_check.stderr.strip()}")

    commit_result = _run_git(repo_path, ["commit", "-m", commit_message, "--", *pathspecs], check=False)
    if commit_result.returncode == 0:
        return True
    if "nothing to commit" in commit_result.stderr.lower():
        return False
    raise RuntimeError(f"git commit failed: {commit_result.stderr.strip()}")


def commit_app_changes(
    tenant_id: int,
    app_id: int,
    *,
    environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    commit_message: str,
) -> bool:
    """Stage all app changes in one environment and commit once."""
    repo_path = _require_app_repo(tenant_id, app_id)
    app_root = get_app_path(tenant_id, app_id, environment=environment, create=True)
    pathspec = app_root.relative_to(repo_path).as_posix()

    _run_git(repo_path, ["add", "-A", "--", pathspec], check=True)

    staged_check = _run_git(repo_path, ["diff", "--cached", "--quiet", "--", pathspec], check=False)
    if staged_check.returncode == 0:
        return False
    if staged_check.returncode not in (0, 1):
        raise RuntimeError(f"git diff --cached failed: {staged_check.stderr.strip()}")

    commit_result = _run_git(repo_path, ["commit", "-m", commit_message, "--", pathspec], check=False)
    if commit_result.returncode == 0:
        return True
    if "nothing to commit" in commit_result.stderr.lower():
        return False
    raise RuntimeError(f"git commit failed: {commit_result.stderr.strip()}")


def has_uncommitted_changes(
    tenant_id: int,
    app_id: int,
    *,
    environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
) -> bool:
    """Check if the app environment working tree has uncommitted changes."""
    repo_path = _require_app_repo(tenant_id, app_id)
    app_root = get_app_path(tenant_id, app_id, environment=environment, create=True)
    pathspec = app_root.relative_to(repo_path).as_posix()

    _run_git(repo_path, ["add", "-A", "-n", "--", pathspec], check=True)
    result = _run_git(repo_path, ["status", "--porcelain", "--", pathspec], check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git status failed: {result.stderr.strip()}")
    return bool(result.stdout.strip())


def get_latest_commit_for_app_environment(
    tenant_id: int,
    app_id: int,
    *,
    environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
) -> str | None:
    """Return latest commit SHA that touched one app environment path."""
    repo_path = _require_app_repo(tenant_id, app_id)
    app_root = get_app_path(tenant_id, app_id, environment=environment, create=True)
    pathspec = app_root.relative_to(repo_path).as_posix()

    log_result = _run_git(repo_path, ["log", "-n", "1", "--format=%H", "--", pathspec], check=False)
    if log_result.returncode != 0:
        raise RuntimeError(f"git log failed: {log_result.stderr.strip()}")
    commit_sha = log_result.stdout.strip()
    return commit_sha or None


def list_app_commits_for_environment(
    tenant_id: int,
    app_id: int,
    *,
    environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    limit: int = 20,
) -> list[dict[str, str | int]]:
    """List recent commits that touched one app environment path."""
    repo_path = _require_app_repo(tenant_id, app_id)
    app_root = get_app_path(tenant_id, app_id, environment=environment, create=True)
    pathspec = app_root.relative_to(repo_path).as_posix()
    max_count = max(1, int(limit))

    log_result = _run_git(
        repo_path,
        ["log", "-n", str(max_count), "--format=%H%x1f%ct%x1f%s", "--", pathspec],
        check=False,
    )
    if log_result.returncode != 0:
        raise RuntimeError(f"git log failed: {log_result.stderr.strip()}")

    commits: list[dict[str, str | int]] = []
    for line in log_result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f", maxsplit=2)
        if len(parts) != 3:
            continue
        sha, unix_ts_str, message = parts
        try:
            unix_ts = int(unix_ts_str)
        except ValueError:
            unix_ts = 0
        commits.append(
            {
                "sha": sha,
                "timestamp_unix": unix_ts,
                "message": message,
            }
        )
    return commits


def is_commit_in_app_environment_history(
    tenant_id: int,
    app_id: int,
    *,
    environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    commit_sha: str,
) -> bool:
    """Return whether commit exists in one app environment path history."""
    repo_path = _require_app_repo(tenant_id, app_id)
    app_root = get_app_path(tenant_id, app_id, environment=environment, create=True)
    pathspec = app_root.relative_to(repo_path).as_posix()
    normalized_commit = (commit_sha or "").strip()
    if not normalized_commit:
        return False

    rev_list_result = _run_git(
        repo_path,
        ["rev-list", "--all", "--", pathspec],
        check=False,
    )
    if rev_list_result.returncode != 0:
        raise RuntimeError(f"git rev-list failed: {rev_list_result.stderr.strip()}")
    return normalized_commit in set(rev_list_result.stdout.splitlines())


def list_app_files_at_commit(
    tenant_id: int,
    app_id: int,
    *,
    environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    commit_sha: str,
) -> list[str]:
    """List app files in one environment at a specific commit."""
    repo_path = _require_app_repo(tenant_id, app_id)
    app_root = get_app_path(tenant_id, app_id, environment=environment, create=True)
    pathspec = app_root.relative_to(repo_path).as_posix()

    tree_result = _run_git(
        repo_path,
        ["ls-tree", "-r", "--name-only", commit_sha, "--", pathspec],
        check=False,
    )
    if tree_result.returncode != 0:
        raise RuntimeError(f"git ls-tree failed: {tree_result.stderr.strip()}")

    prefix = f"{pathspec}/"
    files: list[str] = []
    for absolute_path in tree_result.stdout.splitlines():
        if absolute_path.startswith(prefix):
            relative_path = absolute_path[len(prefix) :]
            if relative_path:
                files.append(relative_path)
    files.sort()
    return files


def read_app_file_at_commit(
    tenant_id: int,
    app_id: int,
    relative_path: str,
    *,
    environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    commit_sha: str,
    validate_suffix: bool = True,
) -> str:
    """Read one app file at a specific commit."""
    repo_path = _require_app_repo(tenant_id, app_id)
    app_root = get_app_path(tenant_id, app_id, environment=environment, create=True)
    file_path = _resolve_app_relative_path(app_root, relative_path)
    if validate_suffix:
        _validate_app_file_suffix(file_path)
    file_spec = file_path.relative_to(repo_path).as_posix()

    show_result = _run_git(repo_path, ["show", f"{commit_sha}:{file_spec}"], check=False)
    if show_result.returncode != 0:
        raise RuntimeError(f"git show failed: {show_result.stderr.strip()}")
    return show_result.stdout
