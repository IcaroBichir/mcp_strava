from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .client import StravaClient

mcp = FastMCP(
    "Strava",
    instructions=(
        "Use these tools to retrieve the authenticated user's Strava data. "
        "Distances are in meters, times in seconds, speeds in m/s. "
        "Always convert to human-readable units (km or miles, min/km or min/mile, "
        "HH:MM:SS) when presenting results."
    ),
)

_SUMMARY_KEYS = {
    "id", "name", "sport_type", "start_date_local",
    "distance", "moving_time", "elapsed_time", "total_elevation_gain",
    "average_speed", "max_speed", "average_heartrate", "max_heartrate",
    "suffer_score", "kudos_count", "achievement_count", "pr_count", "gear_id",
}


def _iso_to_ts(date_str: str, end_of_day: bool = False) -> int:
    dt = datetime.fromisoformat(date_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # Only adjust to end-of-day for date-only strings (no 'T' separator).
    # Checking the raw string avoids rewrites for explicit T00:00:00 datetimes.
    if end_of_day and "T" not in date_str and " " not in date_str:
        dt = dt.replace(hour=23, minute=59, second=59)
    return int(dt.timestamp())


@mcp.tool()
def list_activities(
    limit: int = 30,
    sport_type: Optional[str] = None,
    after: Optional[str] = None,
    before: Optional[str] = None,
) -> list[dict]:
    """
    List the athlete's activities with summary stats.

    Args:
        limit: Number of activities to return (1–200). Default 30.
        sport_type: Filter by sport, e.g. "Run", "Ride", "Swim", "Walk", "WeightTraining",
                    "Hike", "VirtualRide". Case-sensitive.
        after: Only return activities after this date (ISO 8601, e.g. "2025-01-01").
        before: Only return activities before this date (ISO 8601, e.g. "2025-12-31").
    """
    limit = max(1, min(limit, 200))
    client = StravaClient()
    after_ts = _iso_to_ts(after) if after else None
    before_ts = _iso_to_ts(before, end_of_day=True) if before else None

    if sport_type:
        # Paginate until we have enough matching activities or exhaust the API.
        # A single page of 200 may not contain `limit` matching activities when
        # the history is mixed across sport types.
        matched: list[dict] = []
        page = 1
        while len(matched) < limit:
            page_results = client.list_activities(
                per_page=200, page=page, after=after_ts, before=before_ts,
            )
            if not page_results:
                break
            matched.extend(a for a in page_results if a.get("sport_type") == sport_type)
            if len(page_results) < 200:
                break  # reached the last page
            page += 1
        activities = matched
    else:
        activities = client.list_activities(
            per_page=limit, after=after_ts, before=before_ts,
        )

    return [{k: v for k, v in a.items() if k in _SUMMARY_KEYS and v is not None}
            for a in activities[:limit]]


@mcp.tool()
def get_activity(activity_id: int) -> dict:
    """
    Get full details for a single activity, including splits, segment efforts,
    best efforts, and lap data.

    Args:
        activity_id: The Strava activity ID (available from list_activities).
    """
    return StravaClient().get_activity(activity_id)


@mcp.tool()
def get_athlete_stats() -> dict:
    """
    Get the athlete's aggregate training statistics broken down by sport type
    (run, ride, swim) across three windows: recent (last 4 weeks), year-to-date,
    and all-time.

    Returns totals for distance, elevation gain, moving time, and activity count.
    """
    return StravaClient().get_athlete_stats()


@mcp.tool()
def get_athlete() -> dict:
    """
    Get the authenticated athlete's profile: name, location, weight, FTP,
    follower/following counts, and measurement preference (feet or meters).
    """
    athlete = StravaClient().get_athlete()
    keep = {
        "id", "firstname", "lastname", "city", "state", "country",
        "sex", "weight", "follower_count", "friend_count",
        "measurement_preference", "ftp", "created_at",
    }
    return {k: v for k, v in athlete.items() if k in keep and v is not None}


@mcp.tool()
def get_gear(gear_id: str) -> dict:
    """
    Get details for a specific piece of gear (bike or running shoes), including
    name, brand, model, and total distance logged on Strava.

    Args:
        gear_id: The gear ID string (e.g. "b12345" for a bike, "g67890" for shoes).
                 Found in the gear_id field of activity data.
    """
    return StravaClient().get_gear(gear_id)
