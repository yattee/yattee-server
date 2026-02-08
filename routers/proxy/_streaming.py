"""Proxy router definition.

The /proxy/stream/ and /proxy/audio/ endpoints were removed as they were
superseded by /proxy/fast/ (see _fast_download.py). This module retains
only the shared APIRouter instance imported by _fast_download.py and __init__.py.
"""

from fastapi import APIRouter

router = APIRouter(tags=["proxy"])
