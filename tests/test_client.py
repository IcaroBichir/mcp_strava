"""Tests for StravaClient (client.py)."""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_FAKE_TOKENS = {
    "access_token": "fake_access_token",
    "refresh_token": "fake_refresh",
    "expires_at": 9_999_999_999,
    "client_id": "123",
    "client_secret": "secret",
    "athlete_id": 42,
}

_FAKE_TOKENS_NO_ATHLETE_ID = {**_FAKE_TOKENS, "athlete_id": None}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Return a StravaClient with auth mocked out and cache in a temp dir."""
    monkeypatch.setattr("strava_mcp.cache._CACHE_PATH", tmp_path / "cache.db")
    monkeypatch.setattr("strava_mcp.cache.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("strava_mcp.auth.CONFIG_DIR", tmp_path)
    with patch("strava_mcp.client.refresh_if_needed", return_value=_FAKE_TOKENS):
        from strava_mcp.client import StravaClient
        return StravaClient()


@pytest.fixture()
def client_no_athlete(tmp_path, monkeypatch):
    """Return a StravaClient where athlete_id is None in the token data."""
    monkeypatch.setattr("strava_mcp.cache._CACHE_PATH", tmp_path / "cache.db")
    monkeypatch.setattr("strava_mcp.cache.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("strava_mcp.auth.CONFIG_DIR", tmp_path)
    with patch("strava_mcp.client.refresh_if_needed", return_value=_FAKE_TOKENS_NO_ATHLETE_ID):
        from strava_mcp.client import StravaClient
        return StravaClient()


# ---------------------------------------------------------------------------
# _cached_get — cache hit / miss
# ---------------------------------------------------------------------------

class TestCachedGet:
    def test_cold_cache_calls_http(self, client):
        """First call with a cold cache should call _get exactly once."""
        fake_response = {"id": 1, "name": "Test Activity"}
        with patch.object(client, "_get", return_value=fake_response) as mock_get:
            result = client._cached_get("test_key", "/activities/1", ttl=300)
        mock_get.assert_called_once_with("/activities/1")
        assert result == fake_response

    def test_warm_cache_skips_http(self, client):
        """Second call with the same key must NOT call _get again."""
        fake_response = {"id": 1, "name": "Cached Activity"}
        with patch.object(client, "_get", return_value=fake_response) as mock_get:
            client._cached_get("warm_key", "/activities/1", ttl=300)
            result = client._cached_get("warm_key", "/activities/1", ttl=300)
        # _get should only have been called for the first (cold) request.
        assert mock_get.call_count == 1
        assert result == fake_response

    def test_result_written_to_cache_after_http(self, client):
        """After a cache miss, the result must be stored so the next call is a hit."""
        payload = [{"id": 10}, {"id": 11}]
        with patch.object(client, "_get", return_value=payload):
            client._cached_get("list_key", "/athlete/activities", ttl=60)

        # Read directly from the cache store — must be present.
        cached = client._cache.get("list_key")
        assert cached == payload

    def test_different_keys_independent(self, client):
        """Two different cache keys never collide."""
        with patch.object(client, "_get", side_effect=[{"a": 1}, {"b": 2}]) as mock_get:
            r1 = client._cached_get("key_A", "/path/a", ttl=300)
            r2 = client._cached_get("key_B", "/path/b", ttl=300)
        assert r1 == {"a": 1}
        assert r2 == {"b": 2}
        assert mock_get.call_count == 2


# ---------------------------------------------------------------------------
# get_athlete_stats — athlete_id fallback
# ---------------------------------------------------------------------------

class TestGetAthleteStats:
    def test_uses_athlete_id_from_token(self, client):
        """When athlete_id is in the token, no extra get_athlete call is needed."""
        stats_payload = {"recent_run_totals": {}}
        with patch.object(client, "_get", return_value=stats_payload) as mock_get:
            result = client.get_athlete_stats()
        # Should call /athletes/42/stats (athlete_id=42 from _FAKE_TOKENS)
        mock_get.assert_called_once_with("/athletes/42/stats")
        assert result == stats_payload

    def test_falls_back_to_get_athlete_when_no_athlete_id(self, client_no_athlete):
        """When athlete_id is None in the token, it must call get_athlete() first."""
        athlete_payload = {"id": 99, "firstname": "Icaro"}
        stats_payload = {"all_run_totals": {}}
        # _get is called twice: first for /athlete (profile), then for /athletes/99/stats
        with patch.object(
            client_no_athlete, "_get",
            side_effect=[athlete_payload, stats_payload]
        ) as mock_get:
            result = client_no_athlete.get_athlete_stats()

        assert mock_get.call_count == 2
        assert mock_get.call_args_list[0] == call("/athlete")
        assert mock_get.call_args_list[1] == call("/athletes/99/stats")
        assert result == stats_payload

    def test_athlete_id_fallback_uses_cache_on_second_stats_call(self, client_no_athlete):
        """After the first stats call resolves athlete via get_athlete,
        the second stats call should be fully served from cache."""
        athlete_payload = {"id": 55}
        stats_payload = {"ytd_run_totals": {}}
        with patch.object(
            client_no_athlete, "_get",
            side_effect=[athlete_payload, stats_payload]
        ) as mock_get:
            client_no_athlete.get_athlete_stats()
            result = client_no_athlete.get_athlete_stats()

        # Total HTTP calls must still be 2 (both served from cache on 2nd round)
        assert mock_get.call_count == 2
        assert result == stats_payload


# ---------------------------------------------------------------------------
# list_activities — cache key includes params
# ---------------------------------------------------------------------------

class TestListActivitiesCacheKey:
    def test_different_params_produce_different_keys(self, client):
        """Different before/after/page/per_page combos must not share cache entries."""
        payload_a = [{"id": 1}]
        payload_b = [{"id": 2}]
        with patch.object(client, "_get", side_effect=[payload_a, payload_b]) as mock_get:
            r1 = client.list_activities(per_page=10, page=1)
            r2 = client.list_activities(per_page=20, page=1)
        assert r1 == payload_a
        assert r2 == payload_b
        assert mock_get.call_count == 2

    def test_same_params_uses_cache(self, client):
        """Identical params must be served from cache on the second call."""
        payload = [{"id": 5}]
        with patch.object(client, "_get", return_value=payload) as mock_get:
            client.list_activities(per_page=10, page=1, before=None, after=None)
            result = client.list_activities(per_page=10, page=1, before=None, after=None)
        assert mock_get.call_count == 1
        assert result == payload
