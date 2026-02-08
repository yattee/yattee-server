"""Feed and cached videos repository."""

import json
import logging
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from database.connection import get_connection

logger = logging.getLogger(__name__)


def upsert_cached_videos(channel_id: str, site: str, videos: List[Dict[str, Any]]):
    """Insert or update cached videos for a channel. Replaces old videos to keep feed fresh."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Check how many old videos exist before deletion
        cursor.execute(
            """
            SELECT COUNT(*), MIN(published), MAX(published)
            FROM cached_videos
            WHERE channel_id = ? AND site = ?
        """,
            (channel_id, site),
        )
        old_stats = cursor.fetchone()
        old_count = old_stats[0] if old_stats else 0
        old_min_date = old_stats[1] if old_stats else None
        old_max_date = old_stats[2] if old_stats else None

        # Delete all old videos for this channel
        cursor.execute(
            """
            DELETE FROM cached_videos
            WHERE channel_id = ? AND site = ?
        """,
            (channel_id, site),
        )

        # Deduplicate videos by video_id (keep first occurrence)
        seen_video_ids = set()
        unique_videos = []
        duplicate_count = 0
        for video in videos:
            video_id = video.get("video_id", "")
            if video_id and video_id not in seen_video_ids:
                seen_video_ids.add(video_id)
                unique_videos.append(video)
            elif video_id:
                duplicate_count += 1

        if duplicate_count > 0:
            logger.warning(f"Filtered {duplicate_count} duplicate video(s) for {channel_id} ({site})")

        # Insert all unique videos
        new_count = 0
        for video in unique_videos:
            # Serialize thumbnail_data as JSON if present
            thumbnail_data_json = json.dumps(video.get("thumbnails", [])) if video.get("thumbnails") else None

            cursor.execute(
                """
                INSERT OR IGNORE INTO cached_videos (channel_id, site, video_id, title, author, author_id,
                                           length_seconds, view_count, published, published_text,
                                           thumbnail_url, thumbnail_data, video_url, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    channel_id,
                    site,
                    video.get("video_id", ""),
                    video.get("title", ""),
                    video.get("author", ""),
                    video.get("author_id", ""),
                    video.get("length_seconds", 0),
                    video.get("view_count"),
                    video.get("published"),
                    video.get("published_text", ""),
                    video.get("thumbnail_url", ""),
                    thumbnail_data_json,
                    video.get("video_url", ""),
                    datetime.now(UTC).isoformat(),
                ),
            )
            new_count += 1

        conn.commit()

        # Log the cache refresh
        if old_count > 0:
            logger.info(
                f"Refreshed cached videos for {channel_id} ({site}): "
                f"replaced {old_count} old videos (published {old_min_date} to {old_max_date}) "
                f"with {new_count} new videos"
            )
        else:
            logger.info(f"Cached {new_count} videos for new channel {channel_id} ({site})")


def cleanup_old_cached_videos(days: int = 30):
    """Remove videos older than X days."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM cached_videos
            WHERE fetched_at < datetime('now', ?)
        """,
            (f"-{days} days",),
        )
        deleted = cursor.rowcount
        conn.commit()
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old cached videos")
        return deleted


def update_fetch_status(
    channel_id: str,
    site: str,
    success: bool = True,
    error: str = None,
    max_videos_fetched: int = None,
    pagination_limited: bool = False,
    pagination_limit_reason: str = None,
):
    """Update the fetch status for a channel."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO feed_fetch_status (
                channel_id, site, last_fetch, fetch_error,
                max_videos_fetched, pagination_limited, pagination_limit_reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(channel_id, site) DO UPDATE SET
                last_fetch = excluded.last_fetch,
                fetch_error = excluded.fetch_error,
                max_videos_fetched = excluded.max_videos_fetched,
                pagination_limited = excluded.pagination_limited,
                pagination_limit_reason = excluded.pagination_limit_reason
        """,
            (
                channel_id,
                site,
                datetime.now(UTC).isoformat(),
                error if not success else None,
                max_videos_fetched,
                1 if pagination_limited else 0,
                pagination_limit_reason,
            ),
        )
        conn.commit()


def upsert_watched_channels(channels: List[Dict[str, Any]]):
    """Insert or update watched channels, updating last_requested timestamp."""
    with get_connection() as conn:
        cursor = conn.cursor()
        for channel in channels:
            cursor.execute(
                """
                INSERT INTO watched_channels (channel_id, site, channel_name, channel_url, avatar_url, last_requested)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(channel_id, site) DO UPDATE SET
                    channel_name = COALESCE(excluded.channel_name, watched_channels.channel_name),
                    channel_url = COALESCE(excluded.channel_url, watched_channels.channel_url),
                    avatar_url = COALESCE(excluded.avatar_url, watched_channels.avatar_url),
                    last_requested = excluded.last_requested
            """,
                (
                    channel.get("channel_id"),
                    channel.get("site"),
                    channel.get("channel_name"),
                    channel.get("channel_url"),
                    channel.get("avatar_url"),
                    datetime.now(UTC).isoformat(),
                ),
            )
        conn.commit()


def get_all_watched_channels() -> List[Dict[str, Any]]:
    """Get all watched channels for background feed fetching."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT channel_id, site, channel_name, channel_url, avatar_url, last_requested
            FROM watched_channels
            ORDER BY site, channel_id
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_watched_channels_with_status() -> List[Dict[str, Any]]:
    """Get watched channels joined with feed fetch status and video stats for admin UI."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT w.*,
                   f.last_fetch,
                   f.fetch_error,
                   COALESCE(video_stats.video_count, 0) as video_count,
                   video_stats.last_video_published,
                   video_stats.last_video_title
            FROM watched_channels w
            LEFT JOIN feed_fetch_status f ON w.channel_id = f.channel_id AND w.site = f.site
            LEFT JOIN (
                SELECT channel_id,
                       site,
                       COUNT(*) as video_count,
                       MAX(published) as last_video_published,
                       (SELECT title
                        FROM cached_videos cv2
                        WHERE cv2.channel_id = cv.channel_id
                          AND cv2.site = cv.site
                        ORDER BY cv2.published DESC
                        LIMIT 1) as last_video_title
                FROM cached_videos cv
                GROUP BY channel_id, site
            ) video_stats ON w.channel_id = video_stats.channel_id AND w.site = video_stats.site
            ORDER BY w.last_requested DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


def update_channel_metadata(channel_id: str, site: str, subscriber_count: int = None, is_verified: bool = None):
    """Update cached metadata for a watched channel."""
    with get_connection() as conn:
        cursor = conn.cursor()
        updates = ["metadata_updated_at = ?"]
        params = [datetime.now(UTC).isoformat()]

        if subscriber_count is not None:
            updates.append("subscriber_count = ?")
            params.append(subscriber_count)
        if is_verified is not None:
            updates.append("is_verified = ?")
            params.append(1 if is_verified else 0)

        params.extend([channel_id, site])
        cursor.execute(
            f"""
            UPDATE watched_channels
            SET {", ".join(updates)}
            WHERE channel_id = ? AND site = ?
        """,
            params,
        )
        conn.commit()


def get_channels_metadata(channel_ids: List[str], site: str = "youtube") -> List[Dict[str, Any]]:
    """Get cached metadata for multiple channels."""
    if not channel_ids:
        return []
    with get_connection() as conn:
        cursor = conn.cursor()
        placeholders = ",".join(["?"] * len(channel_ids))
        cursor.execute(
            f"""
            SELECT channel_id, subscriber_count, is_verified, metadata_updated_at
            FROM watched_channels
            WHERE channel_id IN ({placeholders}) AND site = ?
        """,
            [*channel_ids, site],
        )
        return [dict(row) for row in cursor.fetchall()]


def cleanup_stale_watched_channels(days: int = 14) -> int:
    """Remove channels not requested in X days. Returns count of deleted channels."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM watched_channels
            WHERE last_requested < datetime('now', ?)
        """,
            (f"-{days} days",),
        )
        deleted = cursor.rowcount
        conn.commit()
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} stale watched channels")
        return deleted


def cleanup_orphaned_cached_videos() -> int:
    """Remove cached videos for channels no longer being watched. Returns count deleted."""
    with get_connection() as conn:
        cursor = conn.cursor()
        # Delete videos where the channel is not in watched_channels
        cursor.execute("""
            DELETE FROM cached_videos
            WHERE NOT EXISTS (
                SELECT 1 FROM watched_channels w
                WHERE w.channel_id = cached_videos.channel_id AND w.site = cached_videos.site
            )
        """)
        deleted = cursor.rowcount
        conn.commit()
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} orphaned cached videos")
        return deleted


def get_cached_channel_ids(channels: List[Dict[str, str]]) -> set:
    """Check which channels have cached videos. Returns set of (channel_id, site) tuples."""
    if not channels:
        return set()

    with get_connection() as conn:
        cursor = conn.cursor()
        # Build query to check for any cached videos for each channel
        placeholders = ",".join(["(?, ?)"] * len(channels))
        params = []
        for ch in channels:
            params.extend([ch.get("channel_id"), ch.get("site")])

        cursor.execute(
            f"""
            SELECT DISTINCT channel_id, site
            FROM cached_videos
            WHERE (channel_id, site) IN ({placeholders})
        """,
            params,
        )

        return {(row["channel_id"], row["site"]) for row in cursor.fetchall()}


def get_errored_channel_ids(channels: List[Dict[str, str]]) -> set:
    """Get channels that have fetch errors. Returns set of (channel_id, site) tuples."""
    if not channels:
        return set()

    with get_connection() as conn:
        cursor = conn.cursor()
        # Build query to check for channels with fetch errors
        placeholders = ",".join(["(?, ?)"] * len(channels))
        params = []
        for ch in channels:
            params.extend([ch.get("channel_id"), ch.get("site")])

        cursor.execute(
            f"""
            SELECT channel_id, site
            FROM feed_fetch_status
            WHERE (channel_id, site) IN ({placeholders})
            AND fetch_error IS NOT NULL
        """,
            params,
        )

        return {(row["channel_id"], row["site"]) for row in cursor.fetchall()}


def get_feed_for_channels(channel_ids: List[Dict[str, str]], limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """Get feed videos for a list of channels, sorted by publish date."""
    if not channel_ids:
        return []

    with get_connection() as conn:
        cursor = conn.cursor()
        # Build query with channel list
        placeholders = ",".join(["(?, ?)"] * len(channel_ids))
        params = []
        for ch in channel_ids:
            params.extend([ch.get("channel_id"), ch.get("site")])
        params.extend([limit, offset])

        cursor.execute(
            f"""
            SELECT *
            FROM cached_videos
            WHERE (channel_id, site) IN ({placeholders})
            ORDER BY published DESC
            LIMIT ? OFFSET ?
        """,
            params,
        )
        return [dict(row) for row in cursor.fetchall()]


def get_feed_count_for_channels(channel_ids: List[Dict[str, str]]) -> int:
    """Get total count of feed videos for a list of channels."""
    if not channel_ids:
        return 0

    with get_connection() as conn:
        cursor = conn.cursor()
        placeholders = ",".join(["(?, ?)"] * len(channel_ids))
        params = []
        for ch in channel_ids:
            params.extend([ch.get("channel_id"), ch.get("site")])

        cursor.execute(
            f"""
            SELECT COUNT(*)
            FROM cached_videos
            WHERE (channel_id, site) IN ({placeholders})
        """,
            params,
        )
        return cursor.fetchone()[0]


def get_subscription_by_channel_id(channel_id: str) -> Optional[Dict[str, Any]]:
    """Get a subscription (watched channel) by channel ID (legacy support).

    This replaces the deprecated `subscriptions` table logic with `watched_channels`.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM watched_channels WHERE channel_id = ?", (channel_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
