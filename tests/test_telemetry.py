"""
test_telemetry.py
Unit and integration tests for TelemetryEngine MSID caching and quota efficiency.
"""

import sqlite3
from unittest.mock import MagicMock
import pytest
from src.telemetry import TelemetryEngine
from src.db import get_db_connection, ensure_db_indexes


def test_ensure_db_indexes_creates_msid_cache(temp_db):
    """Verifies that ensure_db_indexes correctly creates msid_cache table and index."""
    with get_db_connection(temp_db) as conn:
        ensure_db_indexes(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='msid_cache'")
        assert cursor.fetchone() is not None

        cursor.execute("PRAGMA table_info(msid_cache)")
        cols = {row[1] for row in cursor.fetchall()}
        assert "msid" in cols
        assert "artist" in cols
        assert "title" in cols
        assert "resolved_at" in cols


def test_msid_cache_persistence(temp_db, temp_config, monkeypatch):
    """
    Acceptance Criterion 1:
    Manually insert an MSID into msid_cache. Call get_loved_tracks().
    Verify the track is resolved directly from SQLite with 0 requests to /listens.
    """
    with get_db_connection(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO msid_cache (msid, artist, title) VALUES (?, ?, ?)",
            ("msid-test-1234", "Radiohead", "Karma Police")
        )
        conn.commit()

    engine = TelemetryEngine(db_path=temp_db, config_path=temp_config)
    engine.lb_user = "test_user"

    calls = []

    def mock_get(url, *args, **kwargs):
        calls.append(url)
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        if "get-feedback" in url:
            mock_resp.json.return_value = {
                "count": 1,
                "feedback": [
                    {"recording_msid": "msid-test-1234", "score": 1}
                ]
            }
            return mock_resp
        elif "listens" in url:
            pytest.fail("Network request to /listens was made when MSID was already in msid_cache!")
        return mock_resp

    monkeypatch.setattr("requests.get", mock_get)

    loved = engine.get_loved_tracks()

    assert loved == [("Radiohead", "Karma Police")]
    assert len(calls) == 1
    assert "get-feedback" in calls[0]


def test_quota_efficiency(temp_db, temp_config, monkeypatch):
    """
    Acceptance Criterion 2:
    When all loved tracks are cached, get_loved_tracks() performs only 1 request
    to /get-feedback instead of multiple requests to /listens.
    """
    cached_items = [
        ("msid-01", "Artist One", "Song One"),
        ("msid-02", "Artist Two", "Song Two"),
        ("msid-03", "Artist Three", "Song Three"),
    ]
    with get_db_connection(temp_db) as conn:
        cursor = conn.cursor()
        cursor.executemany(
            "INSERT INTO msid_cache (msid, artist, title) VALUES (?, ?, ?)",
            cached_items
        )
        conn.commit()

    engine = TelemetryEngine(db_path=temp_db, config_path=temp_config)
    engine.lb_user = "test_user"

    api_calls = []

    def mock_get(url, *args, **kwargs):
        api_calls.append(url)
        resp = MagicMock()
        resp.status_code = 200
        if "get-feedback" in url:
            resp.json.return_value = {
                "count": 3,
                "feedback": [{"recording_msid": m, "score": 1} for m, _, _ in cached_items]
            }
            return resp
        return resp

    monkeypatch.setattr("requests.get", mock_get)

    loved = engine.get_loved_tracks()

    assert len(loved) == 3
    assert ("Artist One", "Song One") in loved
    assert ("Artist Two", "Song Two") in loved
    assert ("Artist Three", "Song Three") in loved
    # Strictly 1 request to /get-feedback
    assert len(api_calls) == 1
    assert "get-feedback" in api_calls[0]


def test_unresolved_msid_fallback_and_caching(temp_db, temp_config, monkeypatch):
    """
    Acceptance Criterion 3:
    When an MSID is not cached, fetch recent listens once, resolve it,
    and persist into msid_cache for future instant lookups.
    """
    engine = TelemetryEngine(db_path=temp_db, config_path=temp_config)
    engine.lb_user = "test_user"

    api_calls = []

    def mock_get(url, *args, **kwargs):
        api_calls.append(url)
        resp = MagicMock()
        resp.status_code = 200

        if "get-feedback" in url:
            resp.json.return_value = {
                "count": 1,
                "feedback": [{"recording_msid": "msid-uncached-99", "score": 1}]
            }
            return resp
        elif "metadata/lookup" in url:
            # Metadata lookup unavailable
            resp.status_code = 404
            return resp
        elif "listens" in url:
            resp.json.return_value = {
                "payload": {
                    "listens": [
                        {
                            "recording_msid": "msid-uncached-99",
                            "listened_at": 1700000000,
                            "track_metadata": {
                                "artist_name": "New Order",
                                "track_name": "Blue Monday"
                            }
                        }
                    ]
                }
            }
            return resp
        return resp

    monkeypatch.setattr("requests.get", mock_get)

    # First run: resolves via listens fallback and populates msid_cache
    loved = engine.get_loved_tracks()
    assert loved == [("New Order", "Blue Monday")]

    # Verify SQLite msid_cache was populated
    with get_db_connection(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT artist, title FROM msid_cache WHERE msid = 'msid-uncached-99'")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "New Order"
        assert row[1] == "Blue Monday"

    # Second run: must resolve from msid_cache directly (0 calls to /listens)
    api_calls.clear()
    loved_cached = engine.get_loved_tracks()
    assert loved_cached == [("New Order", "Blue Monday")]
    assert len(api_calls) == 1
    assert "get-feedback" in api_calls[0]


def test_process_listens_populates_msid_cache(temp_db, temp_config, monkeypatch):
    """
    Verifies that when process_listens runs, all observed scrobbles
    are automatically cached in msid_cache.
    """
    engine = TelemetryEngine(db_path=temp_db, config_path=temp_config)
    engine.lb_user = "test_user"

    fake_listens = [
        {
            "recording_msid": "msid-auto-scrobble-1",
            "listened_at": 1700001000,
            "track_metadata": {
                "artist_name": "Daft Punk",
                "track_name": "Around the World"
            }
        },
        {
            "recording_msid": "msid-auto-scrobble-2",
            "listened_at": 1700002000,
            "track_metadata": {
                "artist_name": "Justice",
                "track_name": "Genesis"
            }
        }
    ]

    monkeypatch.setattr(engine, "fetch_listens", lambda min_ts: fake_listens)

    engine.process_listens()

    with get_db_connection(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT msid, artist, title FROM msid_cache WHERE msid IN ('msid-auto-scrobble-1', 'msid-auto-scrobble-2')")
        rows = {r[0]: (r[1], r[2]) for r in cursor.fetchall()}

        assert "msid-auto-scrobble-1" in rows
        assert rows["msid-auto-scrobble-1"] == ("Daft Punk", "Around the World")
        assert "msid-auto-scrobble-2" in rows
        assert rows["msid-auto-scrobble-2"] == ("Justice", "Genesis")
