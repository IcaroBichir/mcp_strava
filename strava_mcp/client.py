from __future__ import annotations

import httpx

from .auth import refresh_if_needed

_BASE = "https://www.strava.com/api/v3"


class StravaClient:
    def __init__(self) -> None:
        tokens = refresh_if_needed()
        self._token = tokens["access_token"]
        self._athlete_id: int | None = tokens.get("athlete_id")

    def _get(self, path: str, **params) -> dict | list:
        resp = httpx.get(
            f"{_BASE}{path}",
            headers={"Authorization": f"Bearer {self._token}"},
            params={k: v for k, v in params.items() if v is not None},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def get_athlete(self) -> dict:
        return self._get("/athlete")

    def get_athlete_stats(self) -> dict:
        athlete_id = self._athlete_id or self.get_athlete()["id"]
        return self._get(f"/athletes/{athlete_id}/stats")

    def list_activities(
        self,
        *,
        before: int | None = None,
        after: int | None = None,
        page: int = 1,
        per_page: int = 30,
    ) -> list[dict]:
        return self._get(
            "/athlete/activities",
            before=before,
            after=after,
            page=page,
            per_page=per_page,
        )

    def get_activity(self, activity_id: int) -> dict:
        return self._get(f"/activities/{activity_id}")

    def get_gear(self, gear_id: str) -> dict:
        return self._get(f"/gear/{gear_id}")
