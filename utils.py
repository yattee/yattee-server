"""Utility functions for Yattee Server."""

from fastapi import Request


def get_base_url(request: Request) -> str:
    """Get base URL respecting X-Forwarded-Proto header from reverse proxies.

    When running behind a reverse proxy (like Nginx), the internal connection
    uses HTTP even if the client connected via HTTPS. This function checks
    the X-Forwarded-Proto header to return the correct scheme.
    """
    base_url = str(request.base_url).rstrip("/")

    # Check for reverse proxy header
    forwarded_proto = request.headers.get("X-Forwarded-Proto")
    if forwarded_proto:
        # Replace scheme in URL
        if base_url.startswith("http://") and forwarded_proto.lower() == "https":
            base_url = "https://" + base_url[7:]
        elif base_url.startswith("https://") and forwarded_proto.lower() == "http":
            base_url = "http://" + base_url[8:]

    return base_url
