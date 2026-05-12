"""Tests for ResourceParser - unified parsing for FTS and vector indexing.

This test suite documents the raw_content format contract and ensures
ResourceParser correctly handles all supported resource types.
"""

from langchain_core.documents import Document

from apps.shared.domain.types import (
    RESOURCE_TYPE_API_CONNECTOR,
    RESOURCE_TYPE_ASSET,
    RESOURCE_TYPE_DOCUMENT,
)
from apps.shared.search.parser import (
    ParseResult,
    ResourceParser,
    extract_text_from_raw,
    normalize_for_embedding,
    prepare_search_queries,
    preprocess_for_fts,
    preprocess_text,
    unified_tokenize,
)


class TestNormalizeForEmbedding:
    """Tests for normalize_for_embedding (vector path — no stemming)."""

    def test_lowercase(self):
        assert normalize_for_embedding("Hello World") == "hello world"

    def test_snake_case_split(self):
        assert normalize_for_embedding("follower_count") == "follower count"
        assert normalize_for_embedding("order_item_id") == "order item id"

    def test_kebab_case_split(self):
        assert normalize_for_embedding("follower-count") == "follower count"

    def test_no_stemming(self):
        assert normalize_for_embedding("Unified sale orders") == "unified sale orders"
        assert normalize_for_embedding("running policies") == "running policies"
        assert normalize_for_embedding("users") == "users"

    def test_preserve_chinese(self):
        assert normalize_for_embedding("Hello世界") == "hello世界"

    def test_empty_and_none(self):
        assert normalize_for_embedding("") == ""
        assert normalize_for_embedding(None) == ""


class TestPrepareSearchQueries:
    """Tests for prepare_search_queries hybrid query split."""

    def test_splits_fts_and_vector_queries(self):
        fts_query, vector_query = prepare_search_queries("Unified_Sale-Orders")
        assert fts_query == "Unified_Sale-Orders"
        assert vector_query == "unified sale orders"

    def test_strips_whitespace(self):
        fts_query, vector_query = prepare_search_queries("  orders  ")
        assert fts_query == "orders"
        assert vector_query == "orders"


class TestPreprocessForFts:
    """Tests for preprocess_for_fts / preprocess_text (FTS path — with stemming)."""

    def test_lowercase(self):
        """Test English lowercasing."""
        assert preprocess_for_fts("Hello World") == "hello world"

    def test_snake_case_split(self):
        """Test snake_case splitting with stemming."""
        # Snowball stems 'follower' -> 'follow'; 'count' stays 'count'
        assert preprocess_for_fts("follower_count") == "follow count"
        assert preprocess_for_fts("profile_picture") == "profil pictur"

    def test_kebab_case_split(self):
        """Test kebab-case splitting with stemming."""
        assert preprocess_for_fts("follower-count") == "follow count"
        assert preprocess_for_fts("api-key") == "api key"

    def test_stemming_plural(self):
        """Test English plural stemming."""
        # Snowball stems 'followers' -> 'follow' and 'follower' -> 'follow'
        # so query and indexed text both converge to the same root.
        assert preprocess_for_fts("followers") == "follow"
        assert preprocess_for_fts("orders") == "order"

    def test_stemming_tense(self):
        """Test English verb tense stemming."""
        assert preprocess_for_fts("running") == "run"
        assert preprocess_for_fts("flies") == "fli"

    def test_combined_preprocessing(self):
        """Test Pinterest followers example from requirements.

        Both 'followers' and 'follower' are stemmed to 'follow' by Snowball,
        so queries and indexed content converge to the same root.
        """
        assert preprocess_for_fts("Pinterest followers") == "pinterest follow"

    def test_preserve_chinese(self):
        """Test Chinese text is preserved."""
        assert preprocess_for_fts("Hello世界") == "hello世界"

    def test_empty_and_none(self):
        """Test empty inputs."""
        assert preprocess_for_fts("") == ""
        assert preprocess_for_fts(None) == ""

    def test_idempotent(self):
        """Test preprocessing is idempotent."""
        once = preprocess_for_fts("Pinterest followers")
        twice = preprocess_for_fts(once)
        assert once == twice

    def test_preprocess_text_alias(self):
        assert preprocess_text("followers") == preprocess_for_fts("followers")


class TestUnifiedTokenize:
    """Tests for unified_tokenize function."""

    def test_tokenize_english(self):
        """Test tokenizing English text with preprocessing."""
        text = "Hello world, this is a test."
        result = unified_tokenize(text)
        assert isinstance(result, str)
        assert "hello" in result
        assert "world" in result

    def test_tokenize_chinese(self):
        """Test tokenizing Chinese text."""
        text = "这是一个中文测试"
        result = unified_tokenize(text)
        # Jieba should tokenize Chinese into separate words
        assert isinstance(result, str)
        assert len(result) > 0

    def test_tokenize_mixed(self):
        """Test tokenizing mixed Chinese and English text."""
        text = "Hello世界，this是一个test"
        result = unified_tokenize(text)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_tokenize_empty(self):
        """Test tokenizing empty text."""
        assert unified_tokenize("") == ""
        assert unified_tokenize("   ") == ""
        assert unified_tokenize(None) == ""

    def test_tokenize_punctuation(self):
        """Test that punctuation is preserved as separate tokens."""
        text = "Hello, world! How are you?"
        result = unified_tokenize(text)
        assert isinstance(result, str)
        # Punctuation should be separate tokens
        assert "," in result or "，" in result

    def test_tokenize_with_stemming(self):
        """Test that unified_tokenize applies stemming via preprocess_text."""
        result = unified_tokenize("Pinterest followers")
        assert "pinterest" in result
        # Snowball stems 'followers' -> 'follow'
        assert "follow" in result
        assert "followers" not in result


class TestExtractTextFromRaw:
    """Tests for extract_text_from_raw function."""

    def test_extract_from_flow1_format(self):
        """Test extracting text from Flow 1 format (document, asset, api_connector)."""
        raw_content = {
            "text": "This is the searchable text content",
            "filename": "test.pdf",
            "type": "document",
        }
        result = extract_text_from_raw(raw_content)
        assert result == "This is the searchable text content"

    def test_extract_from_legacy_page_format(self):
        """Test extracting text from legacy page-segmented format."""
        raw_content = {
            "content": [
                {"text": "Page 1 content", "page": 1, "type": "text"},
                {"text": "Page 2 content", "page": 2, "type": "text"},
            ],
            "meta": {"parser": "pypdf", "filename": "test.pdf"},
        }
        result = extract_text_from_raw(raw_content)
        assert "Page 1 content" in result
        assert "Page 2 content" in result
        assert "\n" in result

    def test_extract_from_legacy_string_format(self):
        """Test extracting text from legacy simple string format."""
        raw_content = {
            "content": "Simple string content",
            "meta": {"asset_name": "test_table"},
        }
        result = extract_text_from_raw(raw_content)
        assert result == "Simple string content"

    def test_extract_empty_content(self):
        """Test extracting from empty/invalid content."""
        assert extract_text_from_raw({}) == ""
        assert extract_text_from_raw(None) == ""
        assert extract_text_from_raw({"meta": {}}) == ""

    def test_extract_asset_raw_content(self):
        """Test extracting from asset raw_content format."""
        raw_content = {
            "text": "users (table)\nUser data table\nColumns: id, name, email\nData source: postgres",
            "asset_name": "users",
            "asset_type": "table",
            "data_source_name": "postgres",
            "type": "asset",
        }
        result = extract_text_from_raw(raw_content)
        assert "users (table)" in result
        assert "postgres" in result


class TestResourceParserFromRaw:
    """Tests for ResourceParser.from_raw() - Flow 2 processing."""

    def test_from_raw_document(self):
        """Test processing document raw_content."""
        parser = ResourceParser()
        raw_content = {
            "text": "This is document content for testing.",
            "filename": "test.txt",
            "type": "document",
        }

        result = parser.from_raw(raw_content, RESOURCE_TYPE_DOCUMENT)

        assert isinstance(result, ParseResult)
        assert isinstance(result.tokenized_content, str)
        assert len(result.chunks) == 1
        assert isinstance(result.chunks[0], Document)
        assert result.chunks[0].page_content == "this is document content for testing."

    def test_from_raw_asset(self):
        """Test processing asset raw_content."""
        parser = ResourceParser()
        raw_content = {
            "text": "users (table)\nUser data table\nColumns: id, name\nData source: postgres",
            "asset_name": "users",
            "asset_type": "table",
            "data_source_name": "postgres",
            "type": "asset",
        }

        result = parser.from_raw(raw_content, RESOURCE_TYPE_ASSET)

        assert isinstance(result, ParseResult)
        assert isinstance(result.tokenized_content, str)
        assert len(result.chunks) == 1
        assert isinstance(result.chunks[0], Document)
        assert "users" in result.chunks[0].page_content

    def test_from_raw_api_connector(self):
        """Test processing API connector raw_content."""
        parser = ResourceParser()
        raw_content = {
            "text": "GET /api/users\nGet all users\nTags: users, api\nConnector: test_api",
            "method": "GET",
            "path_template": "/api/users",
            "connector_name": "test_api",
            "operation_uid": "test_api_GET_/api/users",
            "type": "api_connector",
        }

        result = parser.from_raw(raw_content, RESOURCE_TYPE_API_CONNECTOR)

        assert isinstance(result, ParseResult)
        assert isinstance(result.tokenized_content, str)
        assert len(result.chunks) == 1
        assert isinstance(result.chunks[0], Document)
        assert "get" in result.chunks[0].page_content

    def test_from_raw_empty_content(self):
        """Test processing empty raw_content."""
        parser = ResourceParser()

        result = parser.from_raw({}, RESOURCE_TYPE_DOCUMENT)

        assert isinstance(result, ParseResult)
        assert result.tokenized_content == ""
        assert result.chunks == []

    def test_from_raw_preserves_metadata(self):
        """Test that metadata is preserved in chunks."""
        parser = ResourceParser()
        raw_content = {
            "text": "Asset content",
            "meta": {
                "asset_name": "test_table",
                "asset_type": "table",
                "data_source_name": "postgres",
                "type": "asset",
            },
        }

        result = parser.from_raw(raw_content, RESOURCE_TYPE_ASSET)

        assert result.chunks[0].metadata.get("asset_name") == "test_table"
        assert result.chunks[0].metadata.get("asset_type") == "table"


class TestRawContentFormatContract:
    """Tests documenting the raw_content format contract.

    These tests ensure all resource types follow the expected format
    for Flow 1 (storage) and Flow 2 (processing).
    """

    def test_document_raw_content_format(self):
        """Document expected format for document raw_content."""
        # Flow 1 format (simple):
        flow1_format = {
            "text": "Extracted text content",
            "filename": "document.pdf",
            "type": "document",
        }

        # Legacy format (page-segmented):
        legacy_format = {
            "content": [
                {"text": "Page 1", "page": 1, "type": "text"},
            ],
            "meta": {"parser": "pypdf", "filename": "document.pdf"},
        }

        # Both should extract to the same text
        assert "Extracted text content" in extract_text_from_raw(flow1_format)
        assert "Page 1" in extract_text_from_raw(legacy_format)

    def test_asset_raw_content_format(self):
        """Document expected format for asset raw_content."""
        # Flow 1 format:
        flow1_format = {
            "text": "users (table)\nUser data",
            "asset_name": "users",
            "asset_type": "table",
            "data_source_name": "postgres",
            "type": "asset",
        }

        # Legacy format:
        legacy_format = {
            "content": "users (table)\nUser data",
            "meta": {"asset_name": "users", "asset_type": "table"},
        }

        # Both should work
        assert "users" in extract_text_from_raw(flow1_format)
        assert "users" in extract_text_from_raw(legacy_format)

    def test_api_connector_raw_content_format(self):
        """Document expected format for API connector raw_content."""
        # Flow 1 format:
        flow1_format = {
            "text": "GET /api/users\nGet all users",
            "method": "GET",
            "path_template": "/api/users",
            "connector_name": "test_api",
            "operation_uid": "test_api_GET_/api/users",
            "type": "api_connector",
        }

        # Legacy format:
        legacy_format = {
            "content": "GET /api/users\nGet all users",
            "meta": {
                "method": "GET",
                "path_template": "/api/users",
                "operation_uid": "test_api_GET_/api/users",
            },
        }

        # Both should work
        assert "GET" in extract_text_from_raw(flow1_format)
        assert "GET" in extract_text_from_raw(legacy_format)
