"""Encryption utilities for sensitive credential storage."""

import os

from cryptography.fernet import Fernet

import config

_fernet_instance = None


def _get_or_create_key() -> bytes:
    """Get encryption key from config or generate and store one."""
    if config.CREDENTIALS_ENCRYPTION_KEY:
        return config.CREDENTIALS_ENCRYPTION_KEY.encode()

    # Check for key file in data directory
    os.makedirs(config.DATA_DIR, exist_ok=True)
    key_file = os.path.join(config.DATA_DIR, ".encryption_key")

    if os.path.exists(key_file):
        with open(key_file, "rb") as f:
            return f.read()

    # Generate new key
    key = Fernet.generate_key()
    with open(key_file, "wb") as f:
        f.write(key)
    # Restrict permissions to owner only
    os.chmod(key_file, 0o600)

    return key


def _get_fernet() -> Fernet:
    """Get or create Fernet instance."""
    global _fernet_instance
    if _fernet_instance is None:
        _fernet_instance = Fernet(_get_or_create_key())
    return _fernet_instance


def encrypt(plaintext: str) -> str:
    """Encrypt a string value.

    Args:
        plaintext: The string to encrypt

    Returns:
        Base64-encoded encrypted string
    """
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt an encrypted string value.

    Args:
        ciphertext: Base64-encoded encrypted string

    Returns:
        Decrypted plaintext string

    Raises:
        cryptography.fernet.InvalidToken: If decryption fails
    """
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()


# Credential types that should be encrypted
SENSITIVE_CREDENTIAL_TYPES = {
    "password",
    "video_password",
    "cookies_file",
    "ap_password",
    "login",  # Combined username/password
}


def should_encrypt(credential_type: str) -> bool:
    """Check if a credential type should be encrypted."""
    return credential_type in SENSITIVE_CREDENTIAL_TYPES
