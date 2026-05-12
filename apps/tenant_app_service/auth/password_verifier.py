"""Password verifier implementations."""

import bcrypt

from apps.tenant_app_service.auth.domain import PasswordVerifier


class BcryptPasswordVerifier(PasswordVerifier):
    """Bcrypt password verifier."""

    def verify(self, password: str, hashed: str) -> bool:
        """Verify password against bcrypt hash."""
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
