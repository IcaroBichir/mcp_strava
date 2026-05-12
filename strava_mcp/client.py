from __future__ import annotations

import httpx

from .auth import refresh_if_needed
from .cache import CacheStore

_BASE = "https://www.strava.com/api/v3"

# TTLs in seconds
_TTL_ACTIVITY = 7 * 24 * 3600   # 7d — activity data is immutable once synced
_TTL_ATHLETE = 24 * 3600         # 24h — profile changes rarely
_TTL_STATS = 3600                 # 1h  — updates after each new activity sync
_TTL_LIST = 3600                  # 60min — new activities come in periodically
_TTL_GEAR = 24 * 3600            # 24h — mileage counter updates occasionally


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

    def get_athlete(self) -> dict:
        return self._cached_get("athlete", "/athlete", _TTL_ATHLETE)

    def get_athlete_stats(self) -> dict:
        athlete_id = self._athlete_id or self.get_athlete()["id"]
        return self._cached_get(
            f"athlete_stats:{athlete_id}",
            f"/athletes/{athlete_id}/stats",
            _TTL_STATS,
        )

    def list_activities(
        self,
        *,
        before: int | None = None,
        after: int | None = None,
        page: int = 1,
        per_page: int = 30,
    ) -> list[dict]:
        key = f"list_activities:before={before}:after={after}:page={page}:per_page={per_page}"
        return self._cached_get(
            key,
            "/athlete/activities",
            _TTL_LIST,
            before=before,
            after=after,
            page=page,
            per_page=per_page,
        )

    def get_activity(self, activity_id: int) -> dict:
        return self._cached_get(
            f"activity:{activity_id}",
            f"/activities/{activity_id}",
            _TTL_ACTIVITY,
        )

    def get_gear(self, gear_id: str) -> dict:
        return self._cached_get(f"gear:{gear_id}", f"/gear/{gear_id}", _TTL_GEAR)
