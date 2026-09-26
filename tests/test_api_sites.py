"""Tests for the admin sites API."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestListSites:
    """GET /api/sites must report the stored proxy_streaming value.

    The list used to omit the field, so the response model default (True) won
    the race and the admin UI always showed stream proxying as enabled, whatever
    the database said.
    """

    def test_proxy_streaming_reflects_database(self, admin_client):
        updated = admin_client.put("/api/sites/1", json={"proxy_streaming": False})
        assert updated.status_code == 200
        assert updated.json()["proxy_streaming"] is False

        sites = {site["id"]: site for site in admin_client.get("/api/sites").json()}
        assert sites[1]["proxy_streaming"] is False

    def test_proxy_streaming_true_after_update(self, admin_client):
        admin_client.put("/api/sites/1", json={"proxy_streaming": True})

        sites = {site["id"]: site for site in admin_client.get("/api/sites").json()}
        assert sites[1]["proxy_streaming"] is True
