"""Stream proxy endpoints for playback and fast downloads."""

# Import _fast_download as side effect to register /fast/{video_id} route on router
import routers.proxy._fast_download as _fast_download  # noqa: F401
from routers.proxy._cleanup import cleanup_old_files_sync, start_cleanup_task
from routers.proxy._streaming import router

__all__ = [
    "router",
    "cleanup_old_files_sync",
    "start_cleanup_task",
]
