"""Tests for redirects behind TLS-terminating reverse proxies."""

import os
import sys

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from server import RelativeRedirectMiddleware


def _client():
    app = FastAPI()

    @app.get("/api/v1/search")
    def search():
        return []

    @app.get("/elsewhere")
    def elsewhere():
        return RedirectResponse("https://example.com/target")

    app.add_middleware(RelativeRedirectMiddleware)
    return TestClient(app, base_url="http://yattee.example")


def test_trailing_slash_redirect_keeps_the_client_scheme():
    response = _client().get("/api/v1/search/?q=test", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/api/v1/search?q=test"


def test_redirects_to_other_hosts_stay_absolute():
    response = _client().get("/elsewhere", follow_redirects=False)

    assert response.headers["location"] == "https://example.com/target"
