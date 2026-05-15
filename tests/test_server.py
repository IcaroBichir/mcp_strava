"""Tests for server.py tool logic — no real HTTP calls."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from strava_mcp.server import _SUMMARY_KEYS, list_activities


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_activities(n: int, sport: str = "Run") -> list[dict]:
    return [
        {
            "id": i,
            "name": f"Activity {i}",
            "sport_type": sport,
            "start_date_local": f"2026-05-{(i % 28) + 1:02d}T08:00:00Z",
            "distance": 5000.0,
            "moving_time": 1800,
            "elapsed_time": 1900,
            "total_elevation_gain": 50.0,
            "average_speed": 2.77,
            "max_speed": 3.5,
        }
        for i in range(n)
    ]


@pytest.fixture()
def mock_client():
    """Patch StravaClient so list_activities never hits the network."""
    with patch("strava_mcp.server.StravaClient") as MockClass:
        instance = MagicMock()
        MockClass.return_value = instance
        yield instance


# ---------------------------------------------------------------------------
# list_activities — limit clamping
# ---------------------------------------------------------------------------

class TestListActivitiesLimitClamping:
    def test_limit_below_1_is_clamped_to_1(self, mock_client):
        mock_client.list_activities_in_range.return_value = _make_activities(5)
        result = list_activities(limit=0)
        assert len(result) <= 1

    def test_limit_above_200_is_clamped_to_200(self, mock_client):
        mock_client.list_activities_in_range.return_value = _make_activities(200)
        result = list_activities(limit=999)
        assert len(result) <= 200

    def test_limit_applied_as_slice(self, mock_client):
        mock_client.list_activities_in_range.return_value = _make_activities(30)
        result = list_activities(limit=10)
        assert len(result) == 10

    def test_limit_larger_than_results_returns_all(self, mock_client):
        mock_client.list_activities_in_range.return_value = _make_activities(5)
        result = list_activities(limit=20)
        assert len(result) == 5


# ---------------------------------------------------------------------------
# list_activities — date range passed to client
# ---------------------------------------------------------------------------

class TestListActivitiesDateRange:
    def test_no_dates_sets_end_to_today(self, mock_client):
        mock_client.list_activities_in_range.return_value = []
        list_activities(limit=30)
        _, end = mock_client.list_activities_in_range.call_args[0]
        assert end == date.today()

    def test_no_dates_start_is_at_least_60_days_back(self, mock_client):
        mock_client.list_activities_in_range.return_value = []
        list_activities(limit=30)
        start, end = mock_client.list_activities_in_range.call_args[0]
        assert (end - start).days >= 60

    def test_before_sets_end_date(self, mock_client):
        mock_client.list_activities_in_range.return_value = []
        list_activities(before="2026-05-10")
        _, end = mock_client.list_activities_in_range.call_args[0]
        assert end == date(2026, 5, 10)

    def test_after_sets_start_date(self, mock_client):
        mock_client.list_activities_in_range.return_value = []
        list_activities(after="2026-05-01", before="2026-05-10")
        start, _ = mock_client.list_activities_in_range.call_args[0]
        assert start == date(2026, 5, 1)

    def test_after_and_before_set_exact_range(self, mock_client):
        mock_client.list_activities_in_range.return_value = []
        list_activities(after="2026-05-01", before="2026-05-10")
        start, end = mock_client.list_activities_in_range.call_args[0]
        assert start == date(2026, 5, 1)
        assert end == date(2026, 5, 10)

    def test_before_with_time_component_uses_date_only(self, mock_client):
        """ISO strings with a time component are truncated to the date part."""
        mock_client.list_activities_in_range.return_value = []
        list_activities(before="2026-05-10T23:59:59")
        _, end = mock_client.list_activities_in_range.call_args[0]
        assert end == date(2026, 5, 10)

    def test_larger_limit_looks_back_further(self, mock_client):
        """With no after date, a larger limit should push start_date further back."""
        mock_client.list_activities_in_range.return_value = []
        list_activities(limit=10)
        start_10, end_10 = mock_client.list_activities_in_range.call_args[0]

        mock_client.list_activities_in_range.return_value = []
        list_activities(limit=100)
        start_100, end_100 = mock_client.list_activities_in_range.call_args[0]

        assert (end_100 - start_100) >= (end_10 - start_10)


# ---------------------------------------------------------------------------
# list_activities — sport_type filtering
# ---------------------------------------------------------------------------

class TestListActivitiesSportTypeFilter:
    def test_sport_type_filter_applied_after_fetch(self, mock_client):
        mixed = _make_activities(3, "Run") + _make_activities(3, "Ride")
        mock_client.list_activities_in_range.return_value = mixed
        result = list_activities(limit=10, sport_type="Run")
        assert all(a["sport_type"] == "Run" for a in result)

    def test_sport_type_filter_respects_limit(self, mock_client):
        runs = _make_activities(10, "Run")
        mock_client.list_activities_in_range.return_value = runs
        result = list_activities(limit=3, sport_type="Run")
        assert len(result) == 3

    def test_no_sport_type_returns_all_sports(self, mock_client):
        mixed = _make_activities(3, "Run") + _make_activities(3, "Ride")
        mock_client.list_activities_in_range.return_value = mixed
        result = list_activities(limit=10)
        sports = {a["sport_type"] for a in result}
        assert "Run" in sports
        assert "Ride" in sports

    def test_sport_type_no_matches_returns_empty(self, mock_client):
        mock_client.list_activities_in_range.return_value = _make_activities(5, "Run")
        result = list_activities(limit=10, sport_type="Swim")
        assert result == []


# ---------------------------------------------------------------------------
# list_activities — _SUMMARY_KEYS filtering
# ---------------------------------------------------------------------------

class TestSummaryKeysFiltering:
    def test_non_summary_keys_stripped(self, mock_client):
        activity = {
            "id": 1,
            "name": "Morning Run",
            "sport_type": "Run",
            "distance": 10000.0,
            "moving_time": 3600,
            "elapsed_time": 3700,
            "total_elevation_gain": 100.0,
            "average_speed": 2.77,
            "max_speed": 3.5,
            # Keys that should be stripped:
            "map": {"id": "xyz", "polyline": "abc"},
            "athlete": {"id": 99},
            "resource_state": 2,
        }
        mock_client.list_activities_in_range.return_value = [activity]
        result = list_activities(limit=1)
        for key in result[0]:
            assert key in _SUMMARY_KEYS

    def test_none_values_stripped(self, mock_client):
        activity = {
            "id": 1,
            "name": "Run",
            "sport_type": "Run",
            "distance": 5000.0,
            "moving_time": 1800,
            "elapsed_time": 1900,
            "average_speed": 2.77,
            "max_speed": 3.0,
            "average_heartrate": None,
            "suffer_score": None,
        }
        mock_client.list_activities_in_range.return_value = [activity]
        result = list_activities(limit=1)
        assert "average_heartrate" not in result[0]
        assert "suffer_score" not in result[0]

    def test_summary_keys_set_contents(self):
        expected = {
            "id", "name", "sport_type", "start_date_local",
            "distance", "moving_time", "elapsed_time", "total_elevation_gain",
            "average_speed", "max_speed", "average_heartrate", "max_heartrate",
            "suffer_score", "kudos_count", "achievement_count", "pr_count", "gear_id",
        }
        assert _SUMMARY_KEYS == expected
