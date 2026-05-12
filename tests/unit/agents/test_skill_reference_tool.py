import json
from pathlib import Path

import pytest

from apps.tenant_app_service.agents.tools.skill_reference import read_skill_file
from apps.tenant_app_service.agents.tools.tool_result import ToolResultStatus


@pytest.fixture
def skill_fixture(tmp_path, monkeypatch):
    old_cwd = Path.cwd()
    monkeypatch.chdir(tmp_path)

    skill_dir = tmp_path / "config" / "skills" / "demo-skill"
    (skill_dir / "references").mkdir(parents=True, exist_ok=True)
    (skill_dir / "references" / "guide.md").write_text(
        "line1\nline2\nline3\nline4\nline5\n",
        encoding="utf-8",
    )
    (skill_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (skill_dir / "scripts" / "tool.py").write_text("print('ok')\n", encoding="utf-8")

    yield skill_dir

    monkeypatch.chdir(old_cwd)


@pytest.mark.asyncio
async def test_read_skill_file_reads_chunk_and_next_line(skill_fixture):
    result = await read_skill_file.coroutine(
        skill_name="demo-skill",
        relative_path="references/guide.md",
        start_line=1,
        max_chars=12,
    )

    assert result.status == ToolResultStatus.SUCCESS
    payload = json.loads(result.content)
    assert payload["content"] == "line1\nline2"
    assert payload["has_more"] is True
    assert payload["next_start_line"] == 3


@pytest.mark.asyncio
async def test_read_skill_file_supports_progressive_loading(skill_fixture):
    first = await read_skill_file.coroutine(
        skill_name="demo-skill",
        relative_path="references/guide.md",
        start_line=1,
        max_chars=20,
    )
    first_payload = json.loads(first.content)

    second = await read_skill_file.coroutine(
        skill_name="demo-skill",
        relative_path="references/guide.md",
        start_line=first_payload["next_start_line"],
        max_chars=20,
    )
    second_payload = json.loads(second.content)

    merged = "\n".join([first_payload["content"], second_payload["content"]])
    assert "line1" in merged
    assert "line5" in merged


@pytest.mark.asyncio
async def test_read_skill_file_allows_non_references_file_under_skill(skill_fixture):
    result = await read_skill_file.coroutine(
        skill_name="demo-skill",
        relative_path="scripts/tool.py",
    )

    assert result.status == ToolResultStatus.SUCCESS
    payload = json.loads(result.content)
    assert "print('ok')" in payload["content"]


@pytest.mark.asyncio
async def test_read_skill_file_rejects_path_traversal(skill_fixture):
    result = await read_skill_file.coroutine(
        skill_name="demo-skill",
        relative_path="../outside.md",
    )

    assert result.status == ToolResultStatus.ERROR
    assert result.error.code == "SKILL_FILE_PATH_TRAVERSAL"


@pytest.mark.asyncio
async def test_read_skill_file_rejects_start_line_out_of_range(skill_fixture):
    result = await read_skill_file.coroutine(
        skill_name="demo-skill",
        relative_path="references/guide.md",
        start_line=999,
    )

    assert result.status == ToolResultStatus.ERROR
    assert result.error.code == "SKILL_FILE_START_LINE_OUT_OF_RANGE"
