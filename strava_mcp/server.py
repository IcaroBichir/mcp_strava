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
    # Date-only strings (no time component) default to midnight; for `before` filters
    # that excludes the entire end date, so shift to 23:59:59 when requested.
    if end_of_day and dt.hour == 0 and dt.minute == 0 and dt.second == 0:
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
    # When filtering by sport_type, fetch the maximum page size so the client-side
    # filter doesn't cause under-delivery (e.g. requesting 30 Runs but getting fewer
    # because the newest 30 activities include other sports).
    per_page = 200 if sport_type else limit
    activities = client.list_activities(
        per_page=per_page,
        after=_iso_to_ts(after) if after else None,
        before=_iso_to_ts(before, end_of_day=True) if before else None,
    )
    if sport_type:
        activities = [a for a in activities if a.get("sport_type") == sport_type]
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
