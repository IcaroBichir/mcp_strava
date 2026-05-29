from __future__ import annotations

from datetime import date, timedelta
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


@mcp.tool()
def list_activities(
    limit: int = 30,
    sport_type: Optional[str] = None,
    after: Optional[str] = None,
    before: Optional[str] = None,
) -> list[dict]:
    """
    List the athlete's activities with summary stats.

    Results are served from a per-day local cache (15-day TTL for past days,
    5-minute TTL for today). Only days missing from the cache trigger API calls,
    so repeated or overlapping requests are cheap.

    Args:
        limit: Number of activities to return (1–200). Default 30.
        sport_type: Filter by sport, e.g. "Run", "Ride", "Swim", "Walk", "WeightTraining",
                    "Hike", "VirtualRide". Case-sensitive.
        after: Only return activities after this date (ISO 8601, e.g. "2025-01-01").
        before: Only return activities before this date (ISO 8601, e.g. "2025-12-31").
    """
    limit = max(1, min(limit, 200))

    end_date = date.fromisoformat(before[:10]) if before else date.today()
    if after:
        start_date = date.fromisoformat(after[:10])
    else:
        # No lower bound given: look back enough days to fill the limit with headroom.
        start_date = end_date - timedelta(days=max(limit * 2, 60))

    client = StravaClient()
    activities = client.list_activities_in_range(start_date, end_date)

    if sport_type:
        activities = [a for a in activities if a.get("sport_type") == sport_type]

    return [
        {k: v for k, v in a.items() if k in _SUMMARY_KEYS and v is not None}
        for a in activities[:limit]
    ]


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
