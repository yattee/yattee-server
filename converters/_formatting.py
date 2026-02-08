"""Date, time, and count formatting utilities."""

from datetime import datetime, timezone
from typing import Optional


def parse_upload_date(upload_date: Optional[str]) -> Optional[int]:
    """Convert yt-dlp upload_date (YYYYMMDD) to Unix timestamp (UTC)."""
    if not upload_date:
        return None
    try:
        dt = datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except ValueError:
        return None


def get_valid_timestamp(info: dict) -> Optional[int]:
    """Get a valid timestamp from yt-dlp info, rejecting epoch/invalid values.

    yt-dlp can return timestamp=0 or release_timestamp=0 for some videos,
    especially shorts with --flat-playlist. This causes "56 years ago" display.
    """
    # Minimum valid timestamp: Jan 1, 2005 (before YouTube existed)
    MIN_VALID_TIMESTAMP = 1104537600

    for key in ("timestamp", "release_timestamp"):
        ts = info.get(key)
        if ts and ts > MIN_VALID_TIMESTAMP:
            return ts
    return None


def format_published_text(upload_date: Optional[str]) -> Optional[str]:
    """Generate human-readable published text."""
    if not upload_date:
        return None
    try:
        dt = datetime.strptime(upload_date, "%Y%m%d")
        delta = datetime.now() - dt
        days = delta.days

        if days == 0:
            return "Today"
        elif days == 1:
            return "1 day ago"
        elif days < 7:
            return f"{days} days ago"
        elif days < 30:
            weeks = days // 7
            return f"{weeks} week{'s' if weeks > 1 else ''} ago"
        elif days < 365:
            months = days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
        else:
            years = days // 365
            return f"{years} year{'s' if years > 1 else ''} ago"
    except ValueError:
        return None


def format_view_count(count: Optional[int]) -> Optional[str]:
    """Format view count as human-readable string."""
    if count is None:
        return None
    if count >= 1_000_000_000:
        return f"{count / 1_000_000_000:.1f}B views"
    elif count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M views"
    elif count >= 1_000:
        return f"{count / 1_000:.1f}K views"
    else:
        return f"{count} views"


def format_subscriber_count(count: Optional[int]) -> Optional[str]:
    """Format subscriber count as human-readable string."""
    if count is None:
        return None
    if count >= 1_000_000_000:
        return f"{count / 1_000_000_000:.1f}B"
    elif count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    elif count >= 1_000:
        return f"{count / 1_000:.1f}K"
    else:
        return str(count)
