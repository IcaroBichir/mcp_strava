"""Tests for CacheStore (cache.py)."""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from strava_mcp.cache import CacheStore


@pytest.fixture()
def cache(tmp_path, monkeypatch):
    """Return a CacheStore backed by a temp SQLite file."""
    monkeypatch.setattr("strava_mcp.cache._CACHE_PATH", tmp_path / "cache.db")
    monkeypatch.setattr("strava_mcp.auth.CONFIG_DIR", tmp_path)
    # Patch CONFIG_DIR used inside CacheStore.__init__ (mkdir call)
    monkeypatch.setattr("strava_mcp.cache.CONFIG_DIR", tmp_path)
    return CacheStore()


# ---------------------------------------------------------------------------
# set / get round-trip
# ---------------------------------------------------------------------------

def test_set_get_dict(cache):
    cache.set("k1", {"foo": "bar", "n": 42}, ttl=300)
    result = cache.get("k1")
    assert result == {"foo": "bar", "n": 42}


def test_set_get_list(cache):
    cache.set("k2", [1, 2, 3], ttl=300)
    result = cache.get("k2")
    assert result == [1, 2, 3]


def test_get_missing_key_returns_none(cache):
    assert cache.get("does_not_exist") is None


# ---------------------------------------------------------------------------
# TTL expiry
# ---------------------------------------------------------------------------

def test_get_returns_none_after_ttl_expired(cache):
    # Store with a 60-second TTL, then fake time advancing past it.
    with patch("strava_mcp.cache.time") as mock_time:
        mock_time.time.return_value = 1_000_000.0
        cache.set("expiring", {"x": 1}, ttl=60)

    # Now time has moved 61 seconds forward — entry should be expired.
    with patch("strava_mcp.cache.time") as mock_time:
        mock_time.time.return_value = 1_000_061.0
        result = cache.get("expiring")

    assert result is None


def test_get_returns_value_before_ttl_expires(cache):
    with patch("strava_mcp.cache.time") as mock_time:
        mock_time.time.return_value = 1_000_000.0
        cache.set("fresh", {"y": 2}, ttl=60)

    # Only 30 seconds have passed — still fresh.
    with patch("strava_mcp.cache.time") as mock_time:
        mock_time.time.return_value = 1_000_030.0
        result = cache.get("fresh")

    assert result == {"y": 2}


def test_expired_entry_is_deleted_from_db(cache):
    """get() on an expired key should remove the row so it doesn't linger."""
    with patch("strava_mcp.cache.time") as mock_time:
        mock_time.time.return_value = 1_000_000.0
        cache.set("gone", {"z": 3}, ttl=10)

    with patch("strava_mcp.cache.time") as mock_time:
        mock_time.time.return_value = 1_000_011.0
        cache.get("gone")  # triggers deletion

    # Inspect the DB directly — row must be gone.
    row = cache._conn.execute(
        "SELECT key FROM cache WHERE key = 'gone'"
    ).fetchone()
    assert row is None


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

def test_clear_returns_correct_count(cache):
    cache.set("a", {"v": 1}, ttl=300)
    cache.set("b", {"v": 2}, ttl=300)
    cache.set("c", {"v": 3}, ttl=300)
    count = cache.clear()
    assert count == 3


def test_clear_on_empty_cache_returns_zero(cache):
    assert cache.clear() == 0


def test_clear_removes_all_entries(cache):
    cache.set("x", [1], ttl=300)
    cache.clear()
    assert cache.get("x") is None


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

def test_stats_structure(cache):
    stats = cache.stats()
    assert set(stats.keys()) == {"total_entries", "expired_entries", "cache_size_bytes"}


def test_stats_total_and_expired(cache):
    with patch("strava_mcp.cache.time") as mock_time:
        mock_time.time.return_value = 1_000_000.0
        cache.set("live1", {"a": 1}, ttl=300)
        cache.set("live2", {"b": 2}, ttl=300)
        cache.set("dead1", {"c": 3}, ttl=10)   # will expire
        cache.set("dead2", {"d": 4}, ttl=10)   # will expire

    # Advance time so the short-TTL entries are expired.
    with patch("strava_mcp.cache.time") as mock_time:
        mock_time.time.return_value = 1_000_020.0
        stats = cache.stats()

    assert stats["total_entries"] == 4
    assert stats["expired_entries"] == 2


def test_stats_cache_size_bytes_positive(cache):
    cache.set("entry", {"data": "hello"}, ttl=300)
    stats = cache.stats()
    assert stats["cache_size_bytes"] > 0
