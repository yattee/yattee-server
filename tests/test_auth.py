"""Tests for auth.py - authentication utilities."""

import os
import sys

import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from auth import (
    hash_password,
    verify_password,
)

# =============================================================================
# Tests for hash_password
# =============================================================================


class TestHashPassword:
    """Tests for hash_password function."""

    def test_returns_string(self):
        """Test that hash_password returns a string."""
        result = hash_password("testpassword")
        assert isinstance(result, str)

    def test_returns_bcrypt_format(self):
        """Test that hash is in bcrypt format."""
        result = hash_password("testpassword")
        # Bcrypt hashes start with $2b$ or $2a$
        assert result.startswith("$2")
        # Bcrypt hashes are 60 characters
        assert len(result) == 60

    def test_different_salts(self):
        """Test that same password produces different hashes (due to salt)."""
        hash1 = hash_password("testpassword")
        hash2 = hash_password("testpassword")
        assert hash1 != hash2

    def test_empty_password(self):
        """Test hashing empty password works."""
        result = hash_password("")
        assert isinstance(result, str)
        assert result.startswith("$2")

    def test_unicode_password(self):
        """Test hashing unicode password works."""
        result = hash_password("пароль密码🔐")
        assert isinstance(result, str)
        assert result.startswith("$2")

    def test_long_password(self):
        """Test hashing password up to bcrypt's 72 byte limit."""
        # bcrypt has a max length of 72 bytes - longer passwords raise ValueError
        max_length_password = "a" * 72
        result = hash_password(max_length_password)
        assert isinstance(result, str)
        assert result.startswith("$2")

    def test_too_long_password_raises(self):
        """Test that passwords over 72 bytes raise ValueError."""
        # bcrypt does not support passwords longer than 72 bytes
        too_long_password = "a" * 100
        with pytest.raises(ValueError, match="72 bytes"):
            hash_password(too_long_password)


# =============================================================================
# Tests for verify_password
# =============================================================================


class TestVerifyPassword:
    """Tests for verify_password function."""

    def test_correct_password(self):
        """Test that correct password verifies."""
        password = "testpassword123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_wrong_password(self):
        """Test that wrong password fails verification."""
        hashed = hash_password("correctpassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_empty_password_correct(self):
        """Test verifying empty password."""
        hashed = hash_password("")
        assert verify_password("", hashed) is True

    def test_empty_password_wrong(self):
        """Test that non-empty password fails against empty hash."""
        hashed = hash_password("")
        assert verify_password("notempty", hashed) is False

    def test_invalid_hash(self):
        """Test that invalid hash returns False."""
        assert verify_password("password", "invalid_hash") is False

    def test_corrupted_hash(self):
        """Test that corrupted hash returns False."""
        assert verify_password("password", "$2b$12$invalidhash") is False

    def test_none_hash(self):
        """Test that None hash returns False gracefully."""
        # This will raise an exception in bcrypt, but our function handles it
        assert verify_password("password", None) is False

    def test_unicode_password_verify(self):
        """Test verifying unicode password."""
        password = "пароль密码🔐"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True
        assert verify_password("different", hashed) is False
