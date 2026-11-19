from apps.shared.audit_event.payload import mask_email, sanitize_audit_payload


def test_mask_email_masks_local_part():
    assert mask_email("user@example.com") == "u***@example.com"


def test_sanitize_audit_payload_strips_secrets():
    cleaned = sanitize_audit_payload(
        {
            "bot_token": "xoxb-secret",
            "fields_changed": ["enabled"],
            "env_var_keys_changed": ["API_KEY"],
        }
    )
    assert "bot_token" not in cleaned
    assert cleaned["fields_changed"] == ["enabled"]
    assert cleaned["env_var_keys_changed"] == ["API_KEY"]


def test_sanitize_audit_payload_keeps_typed_datasource_metadata():
    cleaned = sanitize_audit_payload(
        {
            "config_has_secrets": True,
            "secret_config_changed": True,
            "secret_config_keys": ["password"],
            "password": "must-drop",
        }
    )
    assert cleaned["config_has_secrets"] is True
    assert cleaned["secret_config_changed"] is True
    assert cleaned["secret_config_keys"] == ["password"]
    assert "password" not in cleaned


def test_sanitize_audit_payload_nested_list_of_dicts():
    cleaned = sanitize_audit_payload({"rows": [[{"password": "hunter2"}]]})
    assert cleaned["rows"] == [[{}]]


def test_slack_integration_update_payload_shape():
    cleaned = sanitize_audit_payload(
        {
            "fields_changed": ["channel_chat_enabled", "enabled"],
            "bot_token": "secret",
            "agent_id": 7,
        }
    )
    assert cleaned["fields_changed"] == ["channel_chat_enabled", "enabled"]
    assert cleaned["agent_id"] == 7
    assert "bot_token" not in cleaned