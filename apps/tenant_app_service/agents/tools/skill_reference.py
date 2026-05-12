"""Tools for reading files under a specific skill directory with safe pagination."""

from __future__ import annotations

from pathlib import Path

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.context import extract_runtime_context
from apps.tenant_app_service.agents.tools.tool_result import ToolResult

logger = get_logger(__name__)

DEFAULT_MAX_CHARS = 4000
MAX_MAX_CHARS = 20000
MAX_LINES_PER_CALL = 2000


class ReadSkillFileSchema(BaseModel):
    """Schema for read_skill_file tool."""

    skill_name: str = Field(..., min_length=1, description="Loaded skill name, e.g. weather-ip-helper")
    relative_path: str = Field(..., min_length=1, description="Path relative to skill root, e.g. references/guide.md")
    start_line: int = Field(default=1, ge=1, description="1-based start line for paginated loading")
    max_chars: int = Field(
        default=DEFAULT_MAX_CHARS,
        ge=1,
        le=MAX_MAX_CHARS,
        description="Maximum characters to return in this call",
    )


def _is_within(base: Path, target: Path) -> bool:
    try:
        target.relative_to(base)
        return True
    except ValueError:
        return False


def _reject_hidden_or_cache_paths(path: Path, base: Path) -> bool:
    rel_parts = path.relative_to(base).parts
    blocked = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"}
    return any(part in blocked for part in rel_parts)


@tool(args_schema=ReadSkillFileSchema)
async def read_skill_file(
    skill_name: str,
    relative_path: str,
    start_line: int = 1,
    max_chars: int = 4000,
    config: RunnableConfig = None,
) -> ToolResult:
    """Read text file content from a specific skill directory with paginated loading.

    Security constraints:
    - Can only read files under the resolved skill directory
    - Parent traversal (..) and hidden/cache paths are rejected
    - Returns at most max_chars characters for gradual loading
    """
    skill_name = (skill_name or "").strip()
    relative_path = (relative_path or "").strip().replace("\\", "/")

    if not skill_name:
        return ToolResult.error_result(
            code="SKILL_FILE_INVALID_SKILL",
            message="skill_name must be a non-empty string.",
        )

    if not relative_path:
        return ToolResult.error_result(
            code="SKILL_FILE_INVALID_PATH",
            message="relative_path must be a non-empty string.",
        )

    # Resolve skill path via runtime context when available
    skill_root: Path | None = None
    if config is not None:
        try:
            from apps.tenant_app_service.skills.resolution import get_default_skill_resolver

            runtime = extract_runtime_context(config)
            locator = get_default_skill_resolver().locate(
                skill_name,
                tenant_id=runtime.user.tenant_id,
                user_id=runtime.user.user_id,
            )
            if locator:
                skill_root = Path(locator.host_skill_dir).resolve()
        except Exception:
            logger.exception("Failed to resolve skill path at runtime")

    # Fallback to builtin skills directory
    if skill_root is None:
        skill_root = Path("config/skills").resolve() / skill_name

    if not skill_root.exists() or not skill_root.is_dir():
        return ToolResult.error_result(
            code="SKILL_FILE_SKILL_NOT_FOUND",
            message=f"Skill '{skill_name}' does not exist.",
        )

    target_path = (skill_root / relative_path).resolve()
    if not _is_within(skill_root, target_path):
        return ToolResult.error_result(
            code="SKILL_FILE_PATH_TRAVERSAL",
            message="relative_path must stay within the target skill directory.",
        )

    if _reject_hidden_or_cache_paths(target_path, skill_root):
        return ToolResult.error_result(
            code="SKILL_FILE_PATH_BLOCKED",
            message="Reading from hidden/cache directories is not allowed.",
        )

    if not target_path.exists() or not target_path.is_file():
        return ToolResult.error_result(
            code="SKILL_FILE_NOT_FOUND",
            message=f"File not found: {relative_path}",
        )

    try:
        raw_text = target_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ToolResult.error_result(
            code="SKILL_FILE_NOT_TEXT",
            message="Only UTF-8 text files are supported by this tool.",
        )

    lines = raw_text.splitlines()
    if start_line > len(lines) + 1:
        return ToolResult.error_result(
            code="SKILL_FILE_START_LINE_OUT_OF_RANGE",
            message=f"start_line {start_line} is out of range for file with {len(lines)} lines.",
            metadata={"total_lines": len(lines)},
        )

    current_line = start_line
    end_limit = min(len(lines), start_line - 1 + MAX_LINES_PER_CALL)
    selected: list[str] = []
    consumed_chars = 0

    for idx in range(start_line - 1, end_limit):
        line = lines[idx]
        add_len = len(line) + (1 if selected else 0)
        if selected and consumed_chars + add_len > max_chars:
            break
        if not selected and len(line) > max_chars:
            selected.append(line[:max_chars])
            consumed_chars = max_chars
            current_line = idx + 2
            break
        selected.append(line)
        consumed_chars += add_len
        current_line = idx + 2

    if not selected and start_line == len(lines) + 1:
        content = ""
        has_more = False
        next_start_line = start_line
    else:
        content = "\n".join(selected)
        has_more = current_line <= len(lines)
        next_start_line = current_line if has_more else len(lines) + 1

    logger.info(
        "Read skill file chunk skill=%s path=%s start_line=%s next_start_line=%s chars=%s has_more=%s",
        skill_name,
        relative_path,
        start_line,
        next_start_line,
        len(content),
        has_more,
    )

    return ToolResult.success(
        {
            "skill_name": skill_name,
            "relative_path": relative_path,
            "start_line": start_line,
            "next_start_line": next_start_line,
            "has_more": has_more,
            "total_lines": len(lines),
            "content": content,
        }
    )
