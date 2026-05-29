"""Tests for StravaClient (client.py)."""
from __future__ import annotations

from datetime import date
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
        fake_response = {"id": 1, "name": "Test Activity"}
        with patch.object(client, "_get", return_value=fake_response) as mock_get:
            result = client._cached_get("test_key", "/activities/1", ttl=300)
        mock_get.assert_called_once_with("/activities/1")
        assert result == fake_response

    def test_warm_cache_skips_http(self, client):
        fake_response = {"id": 1, "name": "Cached Activity"}
        with patch.object(client, "_get", return_value=fake_response) as mock_get:
            client._cached_get("warm_key", "/activities/1", ttl=300)
            result = client._cached_get("warm_key", "/activities/1", ttl=300)
        assert mock_get.call_count == 1
        assert result == fake_response

    def test_result_written_to_cache_after_http(self, client):
        payload = [{"id": 10}, {"id": 11}]
        with patch.object(client, "_get", return_value=payload):
            client._cached_get("list_key", "/athlete/activities", ttl=60)
        assert client._cache.get("list_key") == payload

    def test_different_keys_independent(self, client):
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
        stats_payload = {"recent_run_totals": {}}
        with patch.object(client, "_get", return_value=stats_payload) as mock_get:
            result = client.get_athlete_stats()
        mock_get.assert_called_once_with("/athletes/42/stats")
        assert result == stats_payload

    def test_falls_back_to_get_athlete_when_no_athlete_id(self, client_no_athlete):
        athlete_payload = {"id": 99, "firstname": "Icaro"}
        stats_payload = {"all_run_totals": {}}
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
        athlete_payload = {"id": 55}
        stats_payload = {"ytd_run_totals": {}}
        with patch.object(
            client_no_athlete, "_get",
            side_effect=[athlete_payload, stats_payload]
        ) as mock_get:
            client_no_athlete.get_athlete_stats()
            result = client_no_athlete.get_athlete_stats()

        assert mock_get.call_count == 2
        assert result == stats_payload


# ---------------------------------------------------------------------------
# list_activities_in_range — per-day cache logic
# ---------------------------------------------------------------------------

def _make_activity(date_str: str, activity_id: int = 1, sport: str = "Run") -> dict:
    return {"id": activity_id, "start_date_local": f"{date_str}T08:00:00Z", "sport_type": sport}


class TestListActivitiesInRange:
    def test_full_cache_miss_calls_fetch_api(self, client):
        """When no days are cached, _fetch_range_from_api is called."""
        fake = [_make_activity("2026-05-10", 1), _make_activity("2026-05-11", 2)]
        with patch.object(client, "_fetch_range_from_api", return_value=fake):
            result = client.list_activities_in_range(date(2026, 5, 10), date(2026, 5, 11))
        assert {a["id"] for a in result} == {1, 2}

    def test_full_cache_hit_skips_api(self, client):
        """All days cached → zero API calls."""
        client._cache.set("activities_day:2026-05-10", [_make_activity("2026-05-10", 1)], ttl=3600)
        with patch.object(client, "_fetch_range_from_api") as mock_fetch:
            result = client.list_activities_in_range(date(2026, 5, 10), date(2026, 5, 10))
        mock_fetch.assert_not_called()
        assert result[0]["id"] == 1

    def test_partial_hit_only_fetches_missing_days(self, client):
        """Days in cache are skipped; only the contiguous missing range is fetched."""
        client._cache.set("activities_day:2026-05-10", [_make_activity("2026-05-10", 1)], ttl=3600)
        fake = [_make_activity("2026-05-11", 2), _make_activity("2026-05-12", 3)]
        with patch.object(client, "_fetch_range_from_api", return_value=fake) as mock_fetch:
            result = client.list_activities_in_range(date(2026, 5, 10), date(2026, 5, 12))
        # Only one range call covering the two missing days
        mock_fetch.assert_called_once_with(date(2026, 5, 11), date(2026, 5, 12))
        assert {a["id"] for a in result} == {1, 2, 3}

    def test_non_contiguous_missing_days_produce_separate_fetch_calls(self, client):
        """Gaps in the missing-day list produce separate fetch calls per contiguous range."""
        client._cache.set("activities_day:2026-05-11", [_make_activity("2026-05-11", 2)], ttl=3600)
        # Days 10 and 12 are missing; day 11 is cached
        fake_10 = [_make_activity("2026-05-10", 1)]
        fake_12 = [_make_activity("2026-05-12", 3)]
        with patch.object(client, "_fetch_range_from_api",
                          side_effect=[fake_10, fake_12]) as mock_fetch:
            client.list_activities_in_range(date(2026, 5, 10), date(2026, 5, 12))
        assert mock_fetch.call_count == 2
        mock_fetch.assert_any_call(date(2026, 5, 10), date(2026, 5, 10))
        mock_fetch.assert_any_call(date(2026, 5, 12), date(2026, 5, 12))

    def test_fetched_activities_stored_per_day(self, client):
        """After a fetch, each calendar day gets its own cache entry."""
        fake = [_make_activity("2026-05-10", 1), _make_activity("2026-05-11", 2)]
        with patch.object(client, "_fetch_range_from_api", return_value=fake):
            client.list_activities_in_range(date(2026, 5, 10), date(2026, 5, 11))
        cached_10 = client._cache.get("activities_day:2026-05-10")
        cached_11 = client._cache.get("activities_day:2026-05-11")
        assert cached_10 == [_make_activity("2026-05-10", 1)]
        assert cached_11 == [_make_activity("2026-05-11", 2)]

    def test_empty_day_cached_as_empty_list_not_none(self, client):
        """A day with no activities is cached as [] to prevent redundant re-fetches."""
        with patch.object(client, "_fetch_range_from_api", return_value=[]):
            client.list_activities_in_range(date(2026, 5, 10), date(2026, 5, 10))
        cached = client._cache.get("activities_day:2026-05-10")
        assert cached == []  # not None

    def test_second_request_for_same_range_is_fully_cached(self, client):
        """The second call for the same range must not call the API at all."""
        fake = [_make_activity("2026-05-10", 1)]
        with patch.object(client, "_fetch_range_from_api", return_value=fake) as mock_fetch:
            client.list_activities_in_range(date(2026, 5, 10), date(2026, 5, 10))
            client.list_activities_in_range(date(2026, 5, 10), date(2026, 5, 10))
        assert mock_fetch.call_count == 1

    def test_result_ordered_newest_day_first(self, client):
        """Activities from later dates appear before activities from earlier dates."""
        client._cache.set("activities_day:2026-05-10", [_make_activity("2026-05-10", 1)], ttl=3600)
        client._cache.set("activities_day:2026-05-11", [_make_activity("2026-05-11", 2)], ttl=3600)
        result = client.list_activities_in_range(date(2026, 5, 10), date(2026, 5, 11))
        assert result[0]["id"] == 2  # day 11 first
        assert result[1]["id"] == 1

    def test_buffer_activities_outside_requested_range_still_cached(self, client):
        """Activities that land outside [start, end] due to the API buffer are cached
        under their own date key rather than being discarded."""
        # The API (with buffer) returns an activity from May 9, which is outside [10, 11]
        fake = [
            _make_activity("2026-05-09", 0),
            _make_activity("2026-05-10", 1),
            _make_activity("2026-05-11", 2),
        ]
        with patch.object(client, "_fetch_range_from_api", return_value=fake):
            client.list_activities_in_range(date(2026, 5, 10), date(2026, 5, 11))
        # The buffer day (May 9) is cached too
        assert client._cache.get("activities_day:2026-05-09") == [_make_activity("2026-05-09", 0)]


# ---------------------------------------------------------------------------
# _contiguous_ranges helper
# ---------------------------------------------------------------------------

class TestContiguousRanges:
    def test_empty_list(self):
        from strava_mcp.client import _contiguous_ranges
        assert _contiguous_ranges([]) == []

    def test_single_date(self):
        from strava_mcp.client import _contiguous_ranges
        assert _contiguous_ranges([date(2026, 5, 10)]) == [(date(2026, 5, 10), date(2026, 5, 10))]

    def test_two_contiguous_dates(self):
        from strava_mcp.client import _contiguous_ranges
        dates = [date(2026, 5, 10), date(2026, 5, 11)]
        assert _contiguous_ranges(dates) == [(date(2026, 5, 10), date(2026, 5, 11))]

    def test_three_contiguous_dates(self):
        from strava_mcp.client import _contiguous_ranges
        dates = [date(2026, 5, 10), date(2026, 5, 11), date(2026, 5, 12)]
        assert _contiguous_ranges(dates) == [(date(2026, 5, 10), date(2026, 5, 12))]

    def test_two_separate_ranges(self):
        from strava_mcp.client import _contiguous_ranges
        dates = [date(2026, 5, 10), date(2026, 5, 12), date(2026, 5, 13)]
        result = _contiguous_ranges(dates)
        assert result == [
            (date(2026, 5, 10), date(2026, 5, 10)),
            (date(2026, 5, 12), date(2026, 5, 13)),
        ]

    def test_three_separate_single_dates(self):
        from strava_mcp.client import _contiguous_ranges
        dates = [date(2026, 5, 1), date(2026, 5, 5), date(2026, 5, 10)]
        result = _contiguous_ranges(dates)
        assert result == [
            (date(2026, 5, 1), date(2026, 5, 1)),
            (date(2026, 5, 5), date(2026, 5, 5)),
            (date(2026, 5, 10), date(2026, 5, 10)),
        ]

    def test_unsorted_input_is_handled(self):
        from strava_mcp.client import _contiguous_ranges
        dates = [date(2026, 5, 12), date(2026, 5, 10), date(2026, 5, 11)]
        assert _contiguous_ranges(dates) == [(date(2026, 5, 10), date(2026, 5, 12))]
