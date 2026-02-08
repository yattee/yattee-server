"""Tests for encryption module."""

import os
import sys
import tempfile
from unittest.mock import patch

import pytest
from cryptography.fernet import InvalidToken

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import encryption


class TestEncryptDecrypt:
    """Tests for encrypt and decrypt functions."""

    def setup_method(self):
        """Reset encryption state before each test."""
        encryption._fernet_instance = None

    def test_encrypt_returns_string(self):
        """Test that encrypt returns a string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("config.DATA_DIR", tmpdir), patch("config.CREDENTIALS_ENCRYPTION_KEY", None):
                result = encryption.encrypt("test_secret")
                assert isinstance(result, str)
                assert result != "test_secret"

    def test_decrypt_returns_original(self):
        """Test that decrypt returns the original plaintext."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("config.DATA_DIR", tmpdir), patch("config.CREDENTIALS_ENCRYPTION_KEY", None):
                original = "my_secret_password_123"
                encrypted = encryption.encrypt(original)
                decrypted = encryption.decrypt(encrypted)
                assert decrypted == original

    def test_encrypt_different_inputs_different_outputs(self):
        """Test that different inputs produce different encrypted outputs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("config.DATA_DIR", tmpdir), patch("config.CREDENTIALS_ENCRYPTION_KEY", None):
                enc1 = encryption.encrypt("secret1")
                enc2 = encryption.encrypt("secret2")
                assert enc1 != enc2

    def test_encrypt_same_input_different_outputs(self):
        """Test that same input produces different outputs (due to nonce)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("config.DATA_DIR", tmpdir), patch("config.CREDENTIALS_ENCRYPTION_KEY", None):
                enc1 = encryption.encrypt("same_secret")
                enc2 = encryption.encrypt("same_secret")
                # Fernet uses random nonce, so same plaintext produces different ciphertext
                assert enc1 != enc2

    def test_decrypt_invalid_token_raises(self):
        """Test that decrypting invalid ciphertext raises InvalidToken."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("config.DATA_DIR", tmpdir), patch("config.CREDENTIALS_ENCRYPTION_KEY", None):
                # Force initialization
                encryption.encrypt("init")
                with pytest.raises(InvalidToken):
                    encryption.decrypt("invalid_ciphertext")

    def test_encrypt_empty_string(self):
        """Test encrypting and decrypting empty string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("config.DATA_DIR", tmpdir), patch("config.CREDENTIALS_ENCRYPTION_KEY", None):
                encrypted = encryption.encrypt("")
                decrypted = encryption.decrypt(encrypted)
                assert decrypted == ""

    def test_encrypt_unicode(self):
        """Test encrypting and decrypting unicode characters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("config.DATA_DIR", tmpdir), patch("config.CREDENTIALS_ENCRYPTION_KEY", None):
                original = "密码🔐émoji"
                encrypted = encryption.encrypt(original)
                decrypted = encryption.decrypt(encrypted)
                assert decrypted == original

    def test_encrypt_long_string(self):
        """Test encrypting and decrypting a long string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("config.DATA_DIR", tmpdir), patch("config.CREDENTIALS_ENCRYPTION_KEY", None):
                original = "a" * 10000
                encrypted = encryption.encrypt(original)
                decrypted = encryption.decrypt(encrypted)
                assert decrypted == original


class TestKeyManagement:
    """Tests for key management functions."""

    def setup_method(self):
        """Reset encryption state before each test."""
        encryption._fernet_instance = None

    def test_key_persisted_to_file(self):
        """Test that encryption key is persisted to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("config.DATA_DIR", tmpdir), patch("config.CREDENTIALS_ENCRYPTION_KEY", None):
                # First encryption creates key file
                encryption.encrypt("test")
                key_file = os.path.join(tmpdir, ".encryption_key")
                assert os.path.exists(key_file)

    def test_key_reused_across_instances(self):
        """Test that the same key is reused after restart."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("config.DATA_DIR", tmpdir), patch("config.CREDENTIALS_ENCRYPTION_KEY", None):
                # First encryption
                original = "persistent_secret"
                encrypted = encryption.encrypt(original)

                # Simulate restart by resetting instance
                encryption._fernet_instance = None

                # Should still decrypt with same key from file
                decrypted = encryption.decrypt(encrypted)
                assert decrypted == original

    def test_config_key_takes_precedence(self):
        """Test that config key is used when provided."""
        from cryptography.fernet import Fernet

        test_key = Fernet.generate_key().decode()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("config.DATA_DIR", tmpdir), patch("config.CREDENTIALS_ENCRYPTION_KEY", test_key):
                # Encrypt with config key
                original = "config_key_secret"
                encrypted = encryption.encrypt(original)

                # Reset and decrypt - should still work with same config key
                encryption._fernet_instance = None
                decrypted = encryption.decrypt(encrypted)
                assert decrypted == original


class TestShouldEncrypt:
    """Tests for should_encrypt function."""

    def test_password_should_encrypt(self):
        """Test that password type should be encrypted."""
        assert encryption.should_encrypt("password") is True

    def test_video_password_should_encrypt(self):
        """Test that video_password type should be encrypted."""
        assert encryption.should_encrypt("video_password") is True

    def test_cookies_file_should_encrypt(self):
        """Test that cookies_file type should be encrypted."""
        assert encryption.should_encrypt("cookies_file") is True

    def test_ap_password_should_encrypt(self):
        """Test that ap_password type should be encrypted."""
        assert encryption.should_encrypt("ap_password") is True

    def test_login_should_encrypt(self):
        """Test that login type should be encrypted."""
        assert encryption.should_encrypt("login") is True

    def test_username_should_not_encrypt(self):
        """Test that username type should not be encrypted."""
        assert encryption.should_encrypt("username") is False

    def test_referer_should_not_encrypt(self):
        """Test that referer type should not be encrypted."""
        assert encryption.should_encrypt("referer") is False

    def test_unknown_type_should_not_encrypt(self):
        """Test that unknown type should not be encrypted."""
        assert encryption.should_encrypt("some_random_type") is False

    def test_case_sensitive(self):
        """Test that credential type matching is case-sensitive."""
        assert encryption.should_encrypt("PASSWORD") is False
        assert encryption.should_encrypt("Password") is False
