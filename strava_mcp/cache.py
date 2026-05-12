from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from .auth import CONFIG_DIR

_CACHE_PATH = CONFIG_DIR / "cache.db"


class CacheStore:
    def __init__(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(_CACHE_PATH)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache "
            "(key TEXT PRIMARY KEY, data TEXT NOT NULL, expires_at REAL NOT NULL)"
        )
        self._conn.commit()

    def get(self, key: str) -> dict | list | None:
        row = self._conn.execute(
            "SELECT data, expires_at FROM cache WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        data, expires_at = row
        if time.time() > expires_at:
            self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            self._conn.commit()
            return None
        return json.loads(data)

    def set(self, key: str, data: dict | list, ttl: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO cache (key, data, expires_at) VALUES (?, ?, ?)",
            (key, json.dumps(data), time.time() + ttl),
        )
        self._conn.commit()

    def clear(self) -> int:
        count = self._conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        self._conn.execute("DELETE FROM cache")
        self._conn.commit()
        return count

    def stats(self) -> dict:
        now = time.time()
        total = self._conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        expired = self._conn.execute(
            "SELECT COUNT(*) FROM cache WHERE expires_at <= ?", (now,)
        ).fetchone()[0]
        size_bytes = _CACHE_PATH.stat().st_size if _CACHE_PATH.exists() else 0
        return {"total_entries": total, "expired_entries": expired, "cache_size_bytes": size_bytes}
