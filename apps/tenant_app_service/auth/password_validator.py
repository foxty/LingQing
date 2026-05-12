"""Password validation utilities."""

import re

from apps.shared.core.exceptions import ValidationError


def validate_password_complexity(password: str) -> None:
    """Validate password meets complexity requirements.

    Requirements:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one number

    Args:
        password: Password to validate

    Raises:
        ValidationError: If password doesn't meet requirements
    """
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters long")

    if not re.search(r"[A-Z]", password):
        raise ValidationError("Password must contain at least one uppercase letter")

    if not re.search(r"[a-z]", password):
        raise ValidationError("Password must contain at least one lowercase letter")

    if not re.search(r"\d", password):
        raise ValidationError("Password must contain at least one number")
