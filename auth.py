"""Authentication utilities for users."""

import bcrypt


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Bcrypt hash string
    """
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode(), salt).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash.

    Args:
        password: Plain text password to verify
        password_hash: Bcrypt hash to check against

    Returns:
        True if password matches, False otherwise
    """
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except (ValueError, TypeError, AttributeError):
        # ValueError: invalid hash format, TypeError: encoding issues
        # AttributeError: None passed as hash
        return False
