"""
Session-based authentication for the Streamlit UI.

Configuration (environment variables)
--------------------------------------
  AUTH_ENABLED        "true" to require login before accessing the app.
                      Default: "false" (disabled for local development).
  AUTH_USERNAME       Accepted username.  Default: "admin".
  AUTH_PASSWORD_HASH  SHA-256 hex digest of the accepted password.
                      Default: SHA-256("changeme") — CHANGE IN PRODUCTION.

Generating a password hash::

    python -c "import hashlib; print(hashlib.sha256(b'yourpassword').hexdigest())"

Security properties
-------------------
  - Passwords are stored only as SHA-256 hashes; plaintext is never retained.
  - ``hmac.compare_digest`` provides constant-time comparison to prevent
    timing-based enumeration attacks.
  - Session tokens use ``secrets.token_hex(32)`` (256 bits of entropy) and
    are never written to logs.
"""
import hashlib
import hmac
import logging
import os
import secrets

logger = logging.getLogger(__name__)

_AUTH_ENABLED: bool = os.getenv("AUTH_ENABLED", "false").lower() == "true"
_USERNAME: str = os.getenv("AUTH_USERNAME", "admin")
# Default hash is SHA-256("changeme").  Override via AUTH_PASSWORD_HASH in .env.
_PASSWORD_HASH: str = os.getenv(
    "AUTH_PASSWORD_HASH",
    hashlib.sha256(b"changeme").hexdigest(),
)


def is_auth_enabled() -> bool:
    """Return ``True`` when ``AUTH_ENABLED=true`` is set in the environment."""
    return _AUTH_ENABLED


def verify_credentials(username: str, password: str) -> bool:
    """
    Verify *username* and *password* against configured credentials.

    Returns ``True`` only when both the username and the hashed password
    match.  Empty strings are rejected immediately without hashing to avoid
    trivial bypass.

    Uses ``hmac.compare_digest`` for constant-time comparison to prevent
    timing side-channel attacks.
    """
    if not username or not password:
        logger.warning("[Auth] Login attempt with empty credentials rejected.")
        return False

    # Constant-time username comparison.
    username_ok = hmac.compare_digest(
        username.encode("utf-8"), _USERNAME.encode("utf-8")
    )

    # Hash the supplied password, then compare hashes (also constant-time).
    pw_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    password_ok = hmac.compare_digest(
        pw_hash.encode("utf-8"), _PASSWORD_HASH.encode("utf-8")
    )

    if username_ok and password_ok:
        logger.info("[Auth] Successful login for user '%s'.", username)
        return True

    logger.warning("[Auth] Failed login attempt for user '%s'.", username)
    return False


def generate_session_token() -> str:
    """
    Generate a cryptographically secure session token.

    Returns a 64-character hex string (256 bits of entropy) suitable for
    storing in ``st.session_state`` as a session identifier.
    """
    return secrets.token_hex(32)
