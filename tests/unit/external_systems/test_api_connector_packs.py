from pathlib import Path

from apps.shared.external_systems.packs.loader import ApiConnectorPackCatalog


def test_pack_catalog_loads_minimal_manifest(tmp_path: Path):
    (tmp_path / "test-chat-user.yaml").write_text(
        """
pack_id: test-chat-user
version: 1.2.0
connector:
  name: Test Chat
  base_url: https://api.example.test
oauth:
  authorize_url: https://auth.example.test/authorize
  token_url: https://auth.example.test/token
operations:
  - method: POST
    path: /messages.search
    operation_id: test_search_messages
    summary: Search synthetic messages.
    request_schema: {type: object}
    response_schema: {type: object}
""",
        encoding="utf-8",
    )

    manifest = ApiConnectorPackCatalog(tmp_path).get("test-chat-user")

    assert manifest.pack_ref == "test-chat-user@1"
    assert manifest.connector.credential_mode == "user"
    assert manifest.execution_rules.default_request_encoding == "json"


def test_builtin_slack_pack_is_curated_for_user_oauth():
    manifest = ApiConnectorPackCatalog().get("slack-user")

    assert manifest.connector.auth_type == "oauth2"
    assert manifest.oauth.scope_param == "user_scope"
    assert manifest.oauth.token_response_path == "authed_user"
    assert manifest.execution_rules.success_json_path == "ok"
    assert manifest.agent_instructions is not None
    assert "permalinks" in manifest.agent_instructions
    assert "10–20" in manifest.agent_instructions
    assert "body_truncated" in manifest.agent_instructions
    assert manifest.version == "1.1.1"
    assert set(manifest.oauth.scopes) >= {
        "search:read",
        "users:read",
        "users:read.email",
        "files:read",
    }
    assert {operation.operation_id for operation in manifest.operations} == {
        "slack_search_messages",
        "slack_list_conversations",
        "slack_conversation_info",
        "slack_conversation_history",
        "slack_conversation_replies",
        "slack_conversation_members",
        "slack_user_info",
        "slack_user_lookup_by_email",
        "slack_file_info",
        "slack_get_message_permalink",
    }


def test_builtin_github_pack_is_read_only_and_curated_for_user_oauth():
    manifest = ApiConnectorPackCatalog().get("github-user")

    assert manifest.pack_ref == "github-user@1"
    assert manifest.connector.base_url == "https://api.github.com"
    assert manifest.connector.credential_mode == "user"
    assert set(manifest.oauth.scopes) == {"repo", "read:user", "user:email"}
    assert manifest.execution_rules.default_request_encoding == "json"
    assert manifest.agent_instructions is not None
    assert "read-only" in manifest.agent_instructions
    assert {operation.method for operation in manifest.operations} == {"GET"}
    assert {operation.operation_id for operation in manifest.operations} == {
        "github_get_authenticated_user",
        "github_list_user_repositories",
        "github_search_repositories",
        "github_search_issues_and_pull_requests",
        "github_get_repository",
        "github_list_repository_issues",
        "github_get_issue",
        "github_list_issue_comments",
        "github_list_pull_requests",
        "github_get_pull_request",
    }
