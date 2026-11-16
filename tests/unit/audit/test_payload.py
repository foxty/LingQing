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


def test_sanitize_audit_payload_keeps_credential_metadata():
    cleaned = sanitize_audit_payload(
        {
            "credentials_present": True,
            "credentials_changed": True,
            "credential_field_names": ["password"],
            "password": "must-drop",
        }
    )
    assert cleaned["credentials_present"] is True
    assert cleaned["credentials_changed"] is True
    assert cleaned["credential_field_names"] == ["password"]
    assert "password" not in cleaned


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