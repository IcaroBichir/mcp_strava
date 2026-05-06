"""Tests for server.py tool logic — no real HTTP calls."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from strava_mcp.server import _iso_to_ts, _SUMMARY_KEYS, list_activities


# ---------------------------------------------------------------------------
# _iso_to_ts
# ---------------------------------------------------------------------------

class TestIsoToTs:
    def test_date_only_no_end_of_day(self):
        """Date-only without end_of_day flag uses midnight (00:00:00 UTC)."""
        ts = _iso_to_ts("2025-01-15")
        from datetime import datetime, timezone
        dt = datetime(2025, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        assert ts == int(dt.timestamp())

    def test_date_only_with_end_of_day(self):
        """Date-only with end_of_day=True should be set to 23:59:59 UTC."""
        ts = _iso_to_ts("2025-01-15", end_of_day=True)
        from datetime import datetime, timezone
        dt = datetime(2025, 1, 15, 23, 59, 59, tzinfo=timezone.utc)
        assert ts == int(dt.timestamp())

    def test_datetime_with_T_ignores_end_of_day(self):
        """Datetime string with 'T' separator must NOT be adjusted even if end_of_day=True."""
        ts = _iso_to_ts("2025-01-15T00:00:00", end_of_day=True)
        from datetime import datetime, timezone
        dt = datetime(2025, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        assert ts == int(dt.timestamp())

    def test_datetime_with_T_preserves_time(self):
        """Explicit time component should be preserved exactly."""
        ts = _iso_to_ts("2025-06-20T14:30:00")
        from datetime import datetime, timezone
        dt = datetime(2025, 6, 20, 14, 30, 0, tzinfo=timezone.utc)
        assert ts == int(dt.timestamp())

    def test_datetime_with_space_separator_ignores_end_of_day(self):
        """Datetime with space separator (not 'T') is also treated as explicit — no end-of-day."""
        ts = _iso_to_ts("2025-01-15 08:00:00", end_of_day=True)
        from datetime import datetime, timezone
        dt = datetime(2025, 1, 15, 8, 0, 0, tzinfo=timezone.utc)
        assert ts == int(dt.timestamp())

    def test_returns_int(self):
        assert isinstance(_iso_to_ts("2025-03-01"), int)


# ---------------------------------------------------------------------------
# list_activities — limit clamping
# ---------------------------------------------------------------------------

def _make_activities(n: int, sport: str = "Run") -> list[dict]:
    return [
        {
            "id": i,
            "name": f"Activity {i}",
            "sport_type": sport,
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


class TestListActivitiesLimitClamping:
    def test_limit_below_1_is_clamped_to_1(self, mock_client):
        mock_client.list_activities.return_value = _make_activities(5)
        result = list_activities(limit=0)
        assert len(result) <= 1

    def test_limit_above_200_is_clamped_to_200(self, mock_client):
        # Return 200 items; the clamp should cap the request at 200.
        mock_client.list_activities.return_value = _make_activities(200)
        list_activities(limit=999)
        # per_page passed to client should be 200 (clamped value)
        call_kwargs = mock_client.list_activities.call_args.kwargs
        assert call_kwargs["per_page"] == 200

    def test_normal_limit_passed_through(self, mock_client):
        mock_client.list_activities.return_value = _make_activities(30)
        list_activities(limit=30)
        call_kwargs = mock_client.list_activities.call_args.kwargs
        assert call_kwargs["per_page"] == 30


# ---------------------------------------------------------------------------
# list_activities — sport_type filtering / pagination
# ---------------------------------------------------------------------------

class TestListActivitiesSportTypeFilter:
    def test_sport_type_filters_mismatched_entries(self, mock_client):
        mixed = _make_activities(3, "Run") + _make_activities(3, "Ride")
        mock_client.list_activities.return_value = mixed
        result = list_activities(limit=10, sport_type="Run")
        assert all(a["sport_type"] == "Run" for a in result)

    def test_sport_type_paginates_until_limit_met(self, mock_client):
        """When sport_type is set, the tool fetches multiple pages until limit is met."""
        # Page 1: 200 activities but only 100 match the sport_type
        page1 = _make_activities(100, "Ride") + _make_activities(100, "Run")
        # Page 2: 200 activities with 100 more matching — now we have 200 matching total
        page2 = _make_activities(100, "Ride") + _make_activities(100, "Run")
        mock_client.list_activities.side_effect = [page1, page2, []]

        result = list_activities(limit=150, sport_type="Ride")
        # limit=150: page1 gives 100 matching (< 150), page2 adds 100 more → truncated to 150
        assert len(result) == 150
        assert mock_client.list_activities.call_count >= 2

    def test_sport_type_stops_when_api_exhausted(self, mock_client):
        """Pagination stops when API returns fewer than per_page=200 results."""
        # Return a partial page (< 200), meaning we've hit the end.
        partial = _make_activities(50, "Run")
        mock_client.list_activities.return_value = partial
        result = list_activities(limit=200, sport_type="Run")
        assert len(result) == 50
        assert mock_client.list_activities.call_count == 1

    def test_no_sport_type_uses_single_request(self, mock_client):
        """Without sport_type, a single client call with per_page=limit is made."""
        mock_client.list_activities.return_value = _make_activities(10)
        list_activities(limit=10)
        assert mock_client.list_activities.call_count == 1


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
            # Fields that should be stripped:
            "map": {"id": "xyz", "polyline": "abc"},
            "athlete": {"id": 99},
            "resource_state": 2,
        }
        mock_client.list_activities.return_value = [activity]
        result = list_activities(limit=1)
        assert len(result) == 1
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
            "total_elevation_gain": 0.0,
            "average_speed": 2.77,
            "max_speed": 3.0,
            "average_heartrate": None,   # None — should be dropped
            "suffer_score": None,         # None — should be dropped
        }
        mock_client.list_activities.return_value = [activity]
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
