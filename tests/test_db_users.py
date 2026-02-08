"""Tests for database/repositories/users.py - User repository functions."""

import os
import sys

import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# =============================================================================
# Tests for user repository functions
# =============================================================================


class TestUserRepository:
    """Tests for user repository functions."""

    @pytest.fixture(autouse=True)
    def setup_test_db(self, test_db):
        """Setup test database for each test."""
        self.db_path = test_db

    def test_has_any_user_empty_db(self):
        """Test has_any_user returns False for empty database."""
        import database

        assert database.has_any_user() is False

    def test_has_any_user_with_user(self):
        """Test has_any_user returns True when user exists."""
        import database

        database.create_user("testuser", "hash123", is_admin=False)
        assert database.has_any_user() is True

    def test_has_any_admin_alias(self):
        """Test has_any_admin is alias for has_any_user."""
        import database

        assert database.has_any_admin() is False
        database.create_user("testuser", "hash123", is_admin=True)
        assert database.has_any_admin() is True

    def test_create_user(self):
        """Test creating a regular user."""
        import database

        user_id = database.create_user("newuser", "passwordhash", is_admin=False)
        assert user_id > 0
        user = database.get_user_by_id(user_id)
        assert user is not None
        assert user["username"] == "newuser"
        assert user["is_admin"] == 0

    def test_create_admin(self):
        """Test creating an admin user."""
        import database

        user_id = database.create_admin("adminuser", "passwordhash")
        assert user_id > 0
        user = database.get_user_by_id(user_id)
        assert user is not None
        assert user["username"] == "adminuser"
        assert user["is_admin"] == 1

    def test_create_user_returns_id(self):
        """Test create_user returns the new user's ID."""
        import database

        user_id1 = database.create_user("user1", "hash1")
        user_id2 = database.create_user("user2", "hash2")
        assert user_id2 > user_id1

    def test_get_user_by_username(self):
        """Test getting user by username."""
        import database

        database.create_user("findme", "hash123")
        user = database.get_user_by_username("findme")
        assert user is not None
        assert user["username"] == "findme"

    def test_get_user_by_username_not_found(self):
        """Test getting non-existent user returns None."""
        import database

        user = database.get_user_by_username("doesnotexist")
        assert user is None

    def test_get_admin_by_username_alias(self):
        """Test get_admin_by_username is alias for get_user_by_username."""
        import database

        database.create_user("admin", "hash", is_admin=True)
        user = database.get_admin_by_username("admin")
        assert user is not None
        assert user["username"] == "admin"

    def test_get_user_by_id(self):
        """Test getting user by ID."""
        import database

        user_id = database.create_user("byid", "hash123")
        user = database.get_user_by_id(user_id)
        assert user is not None
        assert user["id"] == user_id

    def test_get_user_by_id_not_found(self):
        """Test getting non-existent user by ID returns None."""
        import database

        user = database.get_user_by_id(99999)
        assert user is None

    def test_get_admin_by_id_alias(self):
        """Test get_admin_by_id is alias for get_user_by_id."""
        import database

        user_id = database.create_user("admin", "hash", is_admin=True)
        user = database.get_admin_by_id(user_id)
        assert user is not None

    def test_get_all_users(self):
        """Test getting all users."""
        import database

        database.create_user("user1", "hash1", is_admin=False)
        database.create_user("user2", "hash2", is_admin=True)
        users = database.get_all_users()
        assert len(users) == 2
        # Should not include password hash
        assert "password_hash" not in users[0]

    def test_get_all_users_empty(self):
        """Test getting all users when none exist."""
        import database

        users = database.get_all_users()
        assert users == []

    def test_get_all_admins_alias(self):
        """Test get_all_admins is alias for get_all_users."""
        import database

        database.create_user("user1", "hash1", is_admin=False)
        database.create_user("admin1", "hash2", is_admin=True)
        admins = database.get_all_admins()
        # Returns all users (backward compatibility)
        assert len(admins) == 2

    def test_update_user_last_login(self):
        """Test updating user last login timestamp."""
        import database

        user_id = database.create_user("user", "hash")
        user = database.get_user_by_id(user_id)
        assert user["last_login"] is None

        database.update_user_last_login(user_id)
        user = database.get_user_by_id(user_id)
        assert user["last_login"] is not None

    def test_update_admin_last_login_alias(self):
        """Test update_admin_last_login is alias for update_user_last_login."""
        import database

        user_id = database.create_user("admin", "hash", is_admin=True)
        database.update_admin_last_login(user_id)
        user = database.get_user_by_id(user_id)
        assert user["last_login"] is not None

    def test_update_user_password(self):
        """Test updating user password."""
        import database

        user_id = database.create_user("user", "oldhash")
        database.update_user_password(user_id, "newhash")
        user = database.get_user_by_id(user_id)
        assert user["password_hash"] == "newhash"

    def test_update_admin_password_alias(self):
        """Test update_admin_password is alias for update_user_password."""
        import database

        user_id = database.create_user("admin", "oldhash", is_admin=True)
        database.update_admin_password(user_id, "newhash")
        user = database.get_user_by_id(user_id)
        assert user["password_hash"] == "newhash"

    def test_update_user_is_admin(self):
        """Test updating user admin status."""
        import database

        user_id = database.create_user("user", "hash", is_admin=False)
        result = database.update_user(user_id, is_admin=True)
        assert result is True
        user = database.get_user_by_id(user_id)
        assert user["is_admin"] == 1

    def test_update_user_no_changes(self):
        """Test update_user with no changes returns False."""
        import database

        user_id = database.create_user("user", "hash")
        result = database.update_user(user_id)
        assert result is False

    def test_delete_user(self):
        """Test deleting a user."""
        import database

        user_id = database.create_user("todelete", "hash")
        result = database.delete_user(user_id)
        assert result is True
        user = database.get_user_by_id(user_id)
        assert user is None

    def test_delete_user_not_found(self):
        """Test deleting non-existent user returns False."""
        import database

        result = database.delete_user(99999)
        assert result is False

    def test_delete_admin_alias(self):
        """Test delete_admin is alias for delete_user."""
        import database

        user_id = database.create_user("admin", "hash", is_admin=True)
        result = database.delete_admin(user_id)
        assert result is True

    def test_count_users(self):
        """Test counting users."""
        import database

        assert database.count_users() == 0
        database.create_user("user1", "hash1")
        assert database.count_users() == 1
        database.create_user("user2", "hash2")
        assert database.count_users() == 2

    def test_count_admin_users(self):
        """Test counting admin users."""
        import database

        assert database.count_admin_users() == 0
        database.create_user("user", "hash", is_admin=False)
        assert database.count_admin_users() == 0
        database.create_user("admin", "hash", is_admin=True)
        assert database.count_admin_users() == 1

    def test_count_admins_alias(self):
        """Test count_admins is alias for count_admin_users."""
        import database

        database.create_user("admin", "hash", is_admin=True)
        assert database.count_admins() == 1

    def test_user_created_at_timestamp(self):
        """Test that created_at timestamp is set on user creation."""
        import database

        user_id = database.create_user("user", "hash")
        user = database.get_user_by_id(user_id)
        assert user["created_at"] is not None

    def test_multiple_users_different_ids(self):
        """Test that multiple users get unique IDs."""
        import database

        id1 = database.create_user("user1", "hash1")
        id2 = database.create_user("user2", "hash2")
        id3 = database.create_user("user3", "hash3")
        assert id1 != id2 != id3
