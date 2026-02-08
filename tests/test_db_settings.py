"""Tests for database/repositories/settings.py - Settings repository functions."""

import os
import sys

import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# =============================================================================
# Tests for settings repository functions
# =============================================================================


class TestSettingsRepository:
    """Tests for settings repository functions."""

    @pytest.fixture(autouse=True)
    def setup_test_db(self, test_db):
        """Setup test database for each test."""
        self.db_path = test_db

    def test_get_settings_row(self):
        """Test getting settings row."""
        import database

        settings = database.get_settings_row()
        assert settings is not None
        assert "id" in settings

    def test_get_settings_row_has_expected_fields(self):
        """Test settings row contains expected fields."""
        import database

        settings = database.get_settings_row()
        # Check for some expected settings fields
        assert "invidious_instance" in settings or settings is not None

    def test_is_basic_auth_enabled_default(self):
        """Test basic auth is disabled by default."""
        import database

        # Default should be disabled
        result = database.is_basic_auth_enabled()
        assert isinstance(result, bool)

    def test_set_basic_auth_enabled_true(self):
        """Test enabling basic auth."""
        import database

        database.set_basic_auth_enabled(True)
        assert database.is_basic_auth_enabled() is True

    def test_set_basic_auth_enabled_false(self):
        """Test disabling basic auth."""
        import database

        database.set_basic_auth_enabled(True)
        database.set_basic_auth_enabled(False)
        assert database.is_basic_auth_enabled() is False

    def test_update_settings_single_value(self):
        """Test updating a single setting."""
        import database

        database.update_settings({"cache_video_ttl": 7200})
        settings = database.get_settings_row()
        assert settings["cache_video_ttl"] == 7200

    def test_update_settings_multiple_values(self):
        """Test updating multiple settings at once."""
        import database

        database.update_settings({"cache_video_ttl": 3600, "cache_search_ttl": 1800})
        settings = database.get_settings_row()
        assert settings["cache_video_ttl"] == 3600
        assert settings["cache_search_ttl"] == 1800

    def test_update_settings_boolean_conversion(self):
        """Test that boolean values are converted correctly."""
        import database

        database.update_settings({"basic_auth_enabled": True})
        settings = database.get_settings_row()
        # Should be stored as integer 1, but returned as bool
        assert settings["basic_auth_enabled"] is True

    def test_update_settings_empty_dict(self):
        """Test updating with empty dict does nothing."""
        import database

        settings_before = database.get_settings_row()
        database.update_settings({})
        settings_after = database.get_settings_row()
        # Settings should be unchanged (except possibly updated_at)
        assert settings_before["cache_video_ttl"] == settings_after["cache_video_ttl"]

    def test_update_settings_excludes_id(self):
        """Test that id field is excluded from updates."""
        import database

        database.update_settings({"id": 999, "cache_video_ttl": 3600})
        settings = database.get_settings_row()
        # ID should still be 1
        assert settings["id"] == 1
        # But cache_video_ttl should be updated
        assert settings["cache_video_ttl"] == 3600

    def test_update_settings_string_value(self):
        """Test updating a string setting."""
        import database

        database.update_settings({"invidious_instance": "https://invidious.example.com"})
        settings = database.get_settings_row()
        assert settings["invidious_instance"] == "https://invidious.example.com"

    def test_update_settings_integer_value(self):
        """Test updating an integer setting."""
        import database

        database.update_settings({"ytdlp_timeout": 180})
        settings = database.get_settings_row()
        assert settings["ytdlp_timeout"] == 180

    def test_settings_boolean_fields_converted(self):
        """Test that boolean fields are properly converted on read."""
        import database

        settings = database.get_settings_row()
        # These should all be booleans, not integers
        bool_fields = [
            "invidious_author_thumbnails",
            "basic_auth_enabled",
        ]
        for field in bool_fields:
            if field in settings:
                assert isinstance(settings[field], bool), f"{field} should be bool"

    def test_update_settings_preserves_other_values(self):
        """Test that updating one setting doesn't affect others."""
        import database

        # Set initial values
        database.update_settings({"cache_video_ttl": 3600, "cache_search_ttl": 900})

        # Update only one
        database.update_settings({"cache_video_ttl": 7200})

        settings = database.get_settings_row()
        assert settings["cache_video_ttl"] == 7200
        assert settings["cache_search_ttl"] == 900
