"""Shared state, file cleanup, and periodic cleanup."""

import asyncio
import logging
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional

import config
from settings import get_settings

logger = logging.getLogger(__name__)

# Track active downloads: video_id+itag -> download info
_active_downloads: Dict[str, dict] = {}
_downloads_lock = asyncio.Lock()
_cleanup_task: Optional[asyncio.Task] = None
_download_semaphore: Optional[asyncio.Semaphore] = None


def get_download_semaphore() -> asyncio.Semaphore:
    """Get the download semaphore, lazily initialized from settings."""
    global _download_semaphore
    if _download_semaphore is None:
        s = get_settings()
        _download_semaphore = asyncio.Semaphore(s.proxy_max_concurrent_downloads)
    return _download_semaphore

# Downloads directory
if config.DOWNLOAD_DIR:
    DOWNLOADS_DIR = Path(config.DOWNLOAD_DIR)
else:
    DOWNLOADS_DIR = Path(tempfile.gettempdir()) / "yattee-server-downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

# Cleanup settings
CLEANUP_INTERVAL = 60  # Check every 60 seconds


def cleanup_old_files_sync():
    """Synchronously clean up old download files (for startup)."""
    if not DOWNLOADS_DIR.exists():
        return

    s = get_settings()
    now = time.time()
    cleaned = 0
    for file_path in DOWNLOADS_DIR.iterdir():
        if file_path.is_file():
            try:
                age = now - file_path.stat().st_mtime
                if age > s.proxy_download_max_age:
                    file_path.unlink()
                    cleaned += 1
            except OSError as e:
                logger.error(f"[Cleanup] Error removing {file_path}: {e}")

    if cleaned > 0:
        logger.info(f"[Cleanup] Startup: removed {cleaned} old files")


async def periodic_cleanup():
    """Periodically clean up old download files and stale tracking entries."""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)

        try:
            s = get_settings()
            now = time.time()
            cleaned_files = 0
            cleaned_entries = 0

            # Clean up old files
            if DOWNLOADS_DIR.exists():
                for file_path in DOWNLOADS_DIR.iterdir():
                    if file_path.is_file():
                        try:
                            age = now - file_path.stat().st_mtime
                            # Check if file is old AND not actively being downloaded
                            async with _downloads_lock:
                                is_active = any(
                                    d.get("path") == file_path and not d.get("complete", False)
                                    for d in _active_downloads.values()
                                )

                            if age > s.proxy_download_max_age and not is_active:
                                file_path.unlink()
                                cleaned_files += 1
                        except OSError as e:
                            logger.error(f"[Cleanup] Error checking {file_path}: {e}")

            # Clean up stale tracking entries older than max age (including stuck ones)
            processes_to_kill = []
            async with _downloads_lock:
                keys_to_remove = []
                for key, info in _active_downloads.items():
                    start_time = info.get("start_time", 0)
                    if now - start_time > s.proxy_download_max_age:
                        keys_to_remove.append(key)
                        process = info.get("process")
                        if process:
                            processes_to_kill.append(process)

                for key in keys_to_remove:
                    del _active_downloads[key]
                    cleaned_entries += 1

            # Kill associated yt-dlp processes outside the lock
            for process in processes_to_kill:
                try:
                    if process.returncode is None:
                        process.kill()
                        await process.wait()
                        logger.info("[Cleanup] Killed stale yt-dlp process")
                except OSError as e:
                    logger.warning(f"[Cleanup] Failed to kill process: {e}")

            if cleaned_files > 0 or cleaned_entries > 0:
                logger.info(f"[Cleanup] Periodic: removed {cleaned_files} files, {cleaned_entries} entries")

        except (OSError, ValueError) as e:
            logger.error(f"[Cleanup] Periodic cleanup error: {e}")


def start_cleanup_task():
    """Start the periodic cleanup task."""
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(periodic_cleanup())
        logger.info("[Cleanup] Started periodic cleanup task")
