"""User repository."""

from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from database.connection import get_connection


def has_any_user() -> bool:
    """Check if any user account exists (for setup flow)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        return cursor.fetchone()[0] > 0


# Backwards compatibility alias
def has_any_admin() -> bool:
    """Check if any admin account exists (for setup flow). Alias for has_any_user."""
    return has_any_user()


def create_user(username: str, password_hash: str, is_admin: bool = False) -> int:
    """Create a new user. Returns the user ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
            (username, password_hash, is_admin),
        )
        conn.commit()
        return cursor.lastrowid


# Backwards compatibility alias
def create_admin(username: str, password_hash: str) -> int:
    """Create a new admin user. Returns the user ID. Alias for create_user with is_admin=True."""
    return create_user(username, password_hash, is_admin=True)


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Get user by username."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        return dict(row) if row else None


# Backwards compatibility alias
def get_admin_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Get admin by username. Alias for get_user_by_username."""
    return get_user_by_username(username)


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user by ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


# Backwards compatibility alias
def get_admin_by_id(admin_id: int) -> Optional[Dict[str, Any]]:
    """Get admin by ID. Alias for get_user_by_id."""
    return get_user_by_id(admin_id)


def get_all_users() -> List[Dict[str, Any]]:
    """Get all users (without password hashes)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, username, is_admin, created_at, last_login
            FROM users
            ORDER BY created_at
        """)
        return [dict(row) for row in cursor.fetchall()]


# Backwards compatibility alias
def get_all_admins() -> List[Dict[str, Any]]:
    """Get all admin users. Alias that returns all users."""
    return get_all_users()


def update_user_last_login(user_id: int):
    """Update user's last login timestamp."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_login = ? WHERE id = ?", (datetime.now(UTC).isoformat(), user_id))
        conn.commit()


# Backwards compatibility alias
def update_admin_last_login(admin_id: int):
    """Update admin's last login timestamp. Alias for update_user_last_login."""
    update_user_last_login(admin_id)


def update_user_password(user_id: int, password_hash: str):
    """Update user's password."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
        conn.commit()


# Backwards compatibility alias
def update_admin_password(admin_id: int, password_hash: str):
    """Update admin's password. Alias for update_user_password."""
    update_user_password(admin_id, password_hash)


def update_user(user_id: int, is_admin: bool = None) -> bool:
    """Update user's properties. Returns True if updated."""
    updates = []
    params = []

    if is_admin is not None:
        updates.append("is_admin = ?")
        params.append(is_admin)

    if not updates:
        return False

    params.append(user_id)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        return cursor.rowcount > 0


def delete_user(user_id: int) -> bool:
    """Delete a user. Returns True if deleted."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount > 0


# Backwards compatibility alias
def delete_admin(admin_id: int) -> bool:
    """Delete an admin user. Alias for delete_user."""
    return delete_user(admin_id)


def count_users() -> int:
    """Get the total number of users."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        return cursor.fetchone()[0]


def count_admin_users() -> int:
    """Get the total number of admin users."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
        return cursor.fetchone()[0]


# Backwards compatibility alias
def count_admins() -> int:
    """Get the total number of admin users. Alias for count_admin_users."""
    return count_admin_users()
