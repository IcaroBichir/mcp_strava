from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterator

import httpx

from .auth import refresh_if_needed
from .cache import CacheStore

_BASE = "https://www.strava.com/api/v3"

_TTL_ACTIVITY = 15 * 24 * 3600       # 15d — detailed activity is immutable once synced
_TTL_ATHLETE = 24 * 3600              # 24h — profile changes rarely
_TTL_STATS = 3600                      # 1h  — updates after each new activity
_TTL_GEAR = 24 * 3600                 # 24h — mileage counter updates occasionally
_TTL_DAY_HISTORICAL = 15 * 24 * 3600  # 15d — past day bucket (no new activities expected)
_TTL_DAY_TODAY = 5 * 60               # 5min — today's bucket may still receive activities


def _date_iter(start: date, end: date) -> Iterator[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _contiguous_ranges(dates: list[date]) -> list[tuple[date, date]]:
    """Convert a sorted list of dates into [(start, end), ...] contiguous ranges."""
    if not dates:
        return []
    sorted_dates = sorted(dates)
    ranges: list[tuple[date, date]] = []
    start = end = sorted_dates[0]
    for d in sorted_dates[1:]:
        if d == end + timedelta(days=1):
            end = d
        else:
            ranges.append((start, end))
            start = end = d
    ranges.append((start, end))
    return ranges


class StravaClient:
    def __init__(self) -> None:
        tokens = refresh_if_needed()
        self._token = tokens["access_token"]
        self._athlete_id: int | None = tokens.get("athlete_id")
        self._cache = CacheStore()

    def _get(self, path: str, **params) -> dict | list:
        resp = httpx.get(
            f"{_BASE}{path}",
            headers={"Authorization": f"Bearer {self._token}"},
            params={k: v for k, v in params.items() if v is not None},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def _cached_get(self, key: str, path: str, ttl: int, **params) -> dict | list:
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        result = self._get(path, **params)
        self._cache.set(key, result, ttl)
        return result

    # ── Activity listing (per-day cache) ─────────────────────────────────────

    def list_activities_in_range(self, start: date, end: date) -> list[dict]:
        """Return all activities in [start, end] using per-day cache entries.

        Cache hits are returned immediately; only missing days trigger API calls.
        Each day's activity list is cached with a 15-day TTL (5 min for today).
        Days with zero activities are cached as empty lists to prevent re-fetching.
        Results are returned newest day first.
        """
        today = date.today()
        result_by_day: dict[date, list[dict]] = {}
        missing: list[date] = []

        for d in _date_iter(start, end):
            hit = self._cache.get(f"activities_day:{d.isoformat()}")
            if hit is not None:
                result_by_day[d] = hit
            else:
                missing.append(d)

        if missing:
            for range_start, range_end in _contiguous_ranges(missing):
                fetched = self._fetch_range_from_api(range_start, range_end)

                # Group every fetched activity by its local date
                by_day: dict[date, list[dict]] = {}
                for activity in fetched:
                    local_date_str = activity.get("start_date_local", "")[:10]
                    try:
                        act_date = date.fromisoformat(local_date_str)
                    except ValueError:
                        continue
                    by_day.setdefault(act_date, []).append(activity)

                # Cache all grouped days, including buffer days outside [range_start, range_end].
                # The API fetch includes a ±1-day buffer for timezone safety, so we have complete
                # data for those days too — caching them avoids redundant fetches later.
                for act_date, day_acts in by_day.items():
                    ttl = _TTL_DAY_TODAY if act_date == today else _TTL_DAY_HISTORICAL
                    self._cache.set(f"activities_day:{act_date.isoformat()}", day_acts, ttl)

                # Cache empty-list entries for requested days with no activities
                # so they don't trigger another API call on the next request.
                for d in _date_iter(range_start, range_end):
                    if d not in by_day:
                        ttl = _TTL_DAY_TODAY if d == today else _TTL_DAY_HISTORICAL
                        self._cache.set(f"activities_day:{d.isoformat()}", [], ttl)

                    result_by_day[d] = by_day.get(d, [])

        all_activities: list[dict] = []
        for d in sorted(result_by_day.keys(), reverse=True):
            all_activities.extend(result_by_day[d])
        return all_activities

    def _fetch_range_from_api(self, start: date, end: date) -> list[dict]:
        """Fetch all activities in [start, end] from the API, handling pagination.

        Adds a 1-day buffer on each side to avoid dropping activities near local
        midnight due to UTC offset (Miami is UTC-4/5). The caller groups by
        start_date_local, so the buffer activities land in the correct day bucket.
        """
        fetch_start = start - timedelta(days=1)
        fetch_end = end + timedelta(days=1)
        after_ts = int(datetime(fetch_start.year, fetch_start.month, fetch_start.day,
                                tzinfo=timezone.utc).timestamp())
        before_ts = int(datetime(fetch_end.year, fetch_end.month, fetch_end.day, 23, 59, 59,
                                 tzinfo=timezone.utc).timestamp())

        activities: list[dict] = []
        page = 1
        while True:
            page_data: list = self._get(
                "/athlete/activities",
                before=before_ts,
                after=after_ts,
                per_page=200,
                page=page,
            )
            activities.extend(page_data)
            if len(page_data) < 200:
                break
            page += 1
        return activities

    # ── Single activity ───────────────────────────────────────────────────────

    def get_activity(self, activity_id: int) -> dict:
        return self._cached_get(
            f"activity:{activity_id}",
            f"/activities/{activity_id}",
            _TTL_ACTIVITY,
        )

    # ── Athlete profile & stats ───────────────────────────────────────────────

    def get_athlete(self) -> dict:
        return self._cached_get("athlete", "/athlete", _TTL_ATHLETE)

    def get_athlete_stats(self) -> dict:
        athlete_id = self._athlete_id or self.get_athlete()["id"]
        return self._cached_get(
            f"athlete_stats:{athlete_id}",
            f"/athletes/{athlete_id}/stats",
            _TTL_STATS,
        )

    def get_gear(self, gear_id: str) -> dict:
        return self._cached_get(f"gear:{gear_id}", f"/gear/{gear_id}", _TTL_GEAR)
