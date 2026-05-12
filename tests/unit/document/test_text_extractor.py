"""Unit tests for DocumentTextExtractor.

Tests text extraction and Unicode sanitization for various document formats.
"""

import pytest

from apps.shared.document.text_extractor import DocumentTextExtractor


class TestDocumentTextExtractorSanitize:
    """Tests for sanitize_text static method."""

    def test_sanitize_normal_text(self):
        """Normal text should pass through unchanged (except normalization)."""
        text = "Hello, world! 你好世界"
        result = DocumentTextExtractor.sanitize_text(text)
        assert result == text

    def test_sanitize_empty_text(self):
        """Empty text should return empty."""
        assert DocumentTextExtractor.sanitize_text("") == ""
        assert DocumentTextExtractor.sanitize_text(None) is None

    def test_sanitize_surrogate_pairs(self):
        """Surrogate pairs should be fixed to valid Unicode."""
        # \ud835\udc00 is a surrogate pair for mathematical bold capital A (𝐀)
        text_with_surrogates = "初二物理第9周\ud835\udc00测试"
        result = DocumentTextExtractor.sanitize_text(text_with_surrogates)
        # ftfy should convert surrogate pair to the actual character
        assert "\ud835" not in result
        assert "\udc00" not in result
        assert "初二物理第9周" in result
        assert "测试" in result

    def test_sanitize_isolated_surrogate(self):
        """Isolated surrogate characters should be replaced."""
        # Isolated high surrogate (invalid on its own)
        text_with_isolated_surrogate = "测试\ud835内容"
        result = DocumentTextExtractor.sanitize_text(text_with_isolated_surrogate)
        # Should not raise, and should be valid UTF-8
        result.encode("utf-8")  # Will raise if invalid
        assert "测试" in result or "内容" in result

    def test_sanitize_multiple_surrogate_pairs(self):
        """Multiple surrogate pairs should all be fixed."""
        # Multiple mathematical symbols
        text = "公式: \ud835\udc00 + \ud835\udc01 = \ud835\udc02"
        result = DocumentTextExtractor.sanitize_text(text)
        # Should be valid UTF-8
        result.encode("utf-8")
        assert "\ud835" not in result

    def test_sanitize_mixed_encoding_issues(self):
        """Mixed encoding issues should be handled."""
        # Text with various potential issues
        text = "正常文本\ud835\udc00更多文本\n换行\t制表符"
        result = DocumentTextExtractor.sanitize_text(text)
        # Should be valid UTF-8
        result.encode("utf-8")
        assert "正常文本" in result
        assert "更多文本" in result

    def test_sanitize_preserves_newlines_and_tabs(self):
        """Newlines and tabs should be preserved."""
        text = "Line 1\nLine 2\tTabbed"
        result = DocumentTextExtractor.sanitize_text(text)
        assert result == text

    def test_sanitize_long_text_with_surrogates(self):
        """Long text with surrogates should be handled efficiently."""
        # Simulate a long text with surrogates in the middle
        text = "A" * 5000 + "\ud835\udc00" + "B" * 5000
        result = DocumentTextExtractor.sanitize_text(text)
        # Should be valid UTF-8
        result.encode("utf-8")
        assert len(result) >= 10000
        assert "\ud835" not in result


class TestDocumentTextExtractorExtract:
    """Tests for extract_text method with mocked file storage."""

    @pytest.fixture
    def mock_file_storage(self, tmp_path, monkeypatch):
        """Create a mock file storage that returns local paths."""

        class MockFileStorage:
            def __init__(self, base_path):
                self.base_path = base_path

            async def get_local_path(self, file_url: str) -> str:
                # Return the file URL as local path (assuming it's in tmp_path)
                if file_url.startswith("/"):
                    return file_url
                return str(self.base_path / file_url)

        return MockFileStorage(tmp_path)

    @pytest.mark.asyncio
    async def test_extract_text_unsupported_extension(self, mock_file_storage, tmp_path):
        """Unsupported extensions should return None."""
        extractor = DocumentTextExtractor(mock_file_storage)
        result = await extractor.extract_text("test.xyz", "test.xyz", tenant_id=1)
        assert result is None

    @pytest.mark.asyncio
    async def test_extract_text_file_not_found(self, mock_file_storage, tmp_path):
        """Missing files should return None."""
        extractor = DocumentTextExtractor(mock_file_storage)
        result = await extractor.extract_text("nonexistent.pdf", "nonexistent.pdf", tenant_id=1)
        assert result is None

    @pytest.mark.asyncio
    async def test_extract_text_markdown_file(self, mock_file_storage, tmp_path):
        """Markdown files should be extracted and sanitized."""
        # Create a test markdown file with mathematical symbols (𝐀 = U+1D400)
        md_content = "# Title\n\nContent with 𝐀 symbol\n"
        md_file = tmp_path / "test.md"
        md_file.write_text(md_content, encoding="utf-8")

        extractor = DocumentTextExtractor(mock_file_storage)
        result = await extractor.extract_text(str(md_file), "test.md", tenant_id=1)

        assert result is not None
        assert "Title" in result  # Markdown loader strips # prefix
        assert "𝐀" in result  # Mathematical symbol should be preserved

    @pytest.mark.asyncio
    async def test_extract_text_html_file(self, mock_file_storage, tmp_path):
        """HTML files should be extracted and sanitized."""
        html_content = "<html><body><p>Test 𝐀 content</p></body></html>"
        html_file = tmp_path / "test.html"
        html_file.write_text(html_content, encoding="utf-8")

        extractor = DocumentTextExtractor(mock_file_storage)
        result = await extractor.extract_text(str(html_file), "test.html", tenant_id=1)

        assert result is not None
        assert "Test" in result

    @pytest.mark.asyncio
    async def test_extract_text_empty_file(self, mock_file_storage, tmp_path):
        """Empty files should return None."""
        empty_file = tmp_path / "empty.md"
        empty_file.write_text("", encoding="utf-8")

        extractor = DocumentTextExtractor(mock_file_storage)
        result = await extractor.extract_text(str(empty_file), "empty.md", tenant_id=1)

        assert result is None

    @pytest.mark.asyncio
    async def test_extract_text_xlsx_file(self, mock_file_storage, tmp_path):
        """Excel workbooks should extract sheet names and cell values."""
        import pandas as pd

        xlsx_file = tmp_path / "catalog.xlsx"
        pd.DataFrame({"item": ["widget"], "qty": [3]}).to_excel(xlsx_file, sheet_name="Inventory", index=False)

        extractor = DocumentTextExtractor(mock_file_storage)
        result = await extractor.extract_text(str(xlsx_file), "catalog.xlsx", tenant_id=1)

        assert result is not None
        assert "Inventory" in result
        assert "widget" in result

    @pytest.mark.asyncio
    async def test_extract_text_empty_xlsx_file(self, mock_file_storage, tmp_path):
        """Excel workbooks with no cell values should return None."""
        import pandas as pd

        xlsx_file = tmp_path / "empty.xlsx"
        pd.DataFrame().to_excel(xlsx_file, sheet_name="Empty", index=False)

        extractor = DocumentTextExtractor(mock_file_storage)
        result = await extractor.extract_text(str(xlsx_file), "empty.xlsx", tenant_id=1)

        assert result is None
