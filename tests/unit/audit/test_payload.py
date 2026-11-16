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