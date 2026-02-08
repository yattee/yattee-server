"""Settings repository."""

from typing import Any, Dict, Optional

from database.connection import get_connection


def get_settings_row() -> Optional[Dict[str, Any]]:
    """Get the settings row."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM settings WHERE id = 1")
        row = cursor.fetchone()
        if row:
            result = dict(row)
            # Convert integer booleans to actual booleans
            for key in [
                "invidious_enabled",
                "invidious_author_thumbnails",
                "invidious_proxy_channels",
                "invidious_proxy_channel_tabs",
                "invidious_proxy_videos",
                "invidious_proxy_playlists",
                "invidious_proxy_captions",
                "invidious_proxy_thumbnails",
                "feed_ytdlp_use_flat_playlist",
                "feed_fallback_ytdlp_on_414",
                "feed_fallback_ytdlp_on_error",
                "basic_auth_enabled",
                "allow_all_sites_for_extraction",
            ]:
                if key in result:
                    result[key] = bool(result[key])
            return result
        return None


def is_basic_auth_enabled() -> bool:
    """Check if basic auth is enabled."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT basic_auth_enabled FROM settings WHERE id = 1")
        row = cursor.fetchone()
        return bool(row[0]) if row else False


def set_basic_auth_enabled(enabled: bool) -> None:
    """Enable or disable basic auth."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE settings SET basic_auth_enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
            (1 if enabled else 0,),
        )
        conn.commit()


def update_settings(values: Dict[str, Any]) -> None:
    """Update settings."""
    with get_connection() as conn:
        cursor = conn.cursor()
        # Build SET clause dynamically, excluding id and updated_at
        columns = [k for k in values.keys() if k not in ("id", "updated_at")]
        if not columns:
            return

        # Convert booleans to integers for SQLite
        params = []
        for col in columns:
            val = values[col]
            if isinstance(val, bool):
                val = 1 if val else 0
            params.append(val)

        set_clause = ", ".join(f"{col} = ?" for col in columns)
        set_clause += ", updated_at = CURRENT_TIMESTAMP"

        cursor.execute(f"UPDATE settings SET {set_clause} WHERE id = 1", params)
        conn.commit()
