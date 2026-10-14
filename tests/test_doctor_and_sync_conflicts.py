"""
test_doctor_and_sync_conflicts.py
Unit tests for Syncthing conflict cleaner and system health doctor audit (TASK-05).
"""

import os
import time
from unittest.mock import MagicMock
import pytest
from src.sync import FileSyncManager
from src.paths import StoragePaths
from src.cli import run_doctor
from src.db import get_db_connection


def test_clean_syncthing_conflicts_no_original(temp_env, temp_db, temp_config, dummy_playlists):
    """
    Acceptance Criterion 2a:
    When a conflict file exists without an original file, it should be renamed
    to the original filename.
    """
    paths = StoragePaths(temp_config)
    sync_mgr = FileSyncManager(temp_db, paths, dummy_playlists)

    conveyor_dir = temp_env["conveyor_dir"]
    conflict_file = os.path.join(conveyor_dir, "Track_Name.sync-conflict-20261014-123456-ABC.opus")
    expected_original = os.path.join(conveyor_dir, "Track_Name.opus")

    with open(conflict_file, "wb") as f:
        f.write(b"new conflict audio data")

    assert os.path.exists(conflict_file)
    assert not os.path.exists(expected_original)

    cleaned = sync_mgr.clean_syncthing_conflicts()

    assert cleaned == 1
    assert os.path.exists(expected_original)
    assert not os.path.exists(conflict_file)


def test_clean_syncthing_conflicts_newer_replaces_original(temp_env, temp_db, temp_config, dummy_playlists):
    """
    Acceptance Criterion 2b:
    When the conflict file is newer and larger/equal, it should replace the original file.
    """
    paths = StoragePaths(temp_config)
    sync_mgr = FileSyncManager(temp_db, paths, dummy_playlists)

    permanent_dir = temp_env["permanent_dir"]
    orig_file = os.path.join(permanent_dir, "Artist - Song.opus")
    conflict_file = os.path.join(permanent_dir, "Artist - Song.sync-conflict-20261014-999999-XYZ.opus")

    # Create older original
    with open(orig_file, "wb") as f:
        f.write(b"short")
    os.utime(orig_file, (time.time() - 100, time.time() - 100))

    # Create newer, larger conflict file
    with open(conflict_file, "wb") as f:
        f.write(b"longer updated audio content")
    os.utime(conflict_file, (time.time(), time.time()))

    cleaned = sync_mgr.clean_syncthing_conflicts()

    assert cleaned == 1
    assert os.path.exists(orig_file)
    assert not os.path.exists(conflict_file)
    with open(orig_file, "rb") as f:
        assert f.read() == b"longer updated audio content"


def test_clean_syncthing_conflicts_older_discarded(temp_env, temp_db, temp_config, dummy_playlists):
    """
    Acceptance Criterion 2c:
    When the conflict file is older and smaller, it should simply be removed.
    """
    paths = StoragePaths(temp_config)
    sync_mgr = FileSyncManager(temp_db, paths, dummy_playlists)

    permanent_dir = temp_env["permanent_dir"]
    orig_file = os.path.join(permanent_dir, "Good - Song.opus")
    conflict_file = os.path.join(permanent_dir, "Good - Song.sync-conflict-20261014-111111-AAA.opus")

    # Create newer original
    with open(orig_file, "wb") as f:
        f.write(b"definitive fresh audio content")
    os.utime(orig_file, (time.time(), time.time()))

    # Create older conflict file
    with open(conflict_file, "wb") as f:
        f.write(b"old")
    os.utime(conflict_file, (time.time() - 100, time.time() - 100))

    cleaned = sync_mgr.clean_syncthing_conflicts()

    assert cleaned == 1
    assert os.path.exists(orig_file)
    assert not os.path.exists(conflict_file)
    with open(orig_file, "rb") as f:
        assert f.read() == b"definitive fresh audio content"


def test_doctor_health_audit_execution(temp_db, temp_config, capsys, monkeypatch):
    """
    Acceptance Criterion 1:
    Execute run_doctor and assert it exits with code 0 and outputs all component indicators.
    """
    with get_db_connection(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tracks (id, title, artist, status, duration_seconds, play_count)
            VALUES ('d1', 'Test Song', 'Test Artist', 'CINTA', 200, 3)
        """)
        conn.commit()

    # Mock external network calls to keep unit test completely fast & offline
    mock_resp_lrc = MagicMock()
    mock_resp_lrc.status_code = 200

    mock_resp_lb = MagicMock()
    mock_resp_lb.status_code = 200
    mock_resp_lb.json.return_value = {"valid": True}

    def mock_requests_get(url, *args, **kwargs):
        if "lrclib" in url:
            return mock_resp_lrc
        elif "validate-token" in url:
            return mock_resp_lb
        return MagicMock(status_code=200)

    monkeypatch.setattr("requests.get", mock_requests_get)

    code = run_doctor(db_path=temp_db, config_path=temp_config)
    assert code == 0

    captured = capsys.readouterr().out
    assert "MUSIC ENGINE SYSTEM HEALTH AUDIT (DOCTOR)" in captured
    assert "SQLite Database:" in captured
    assert "Storage Paths:" in captured
    assert "LRCLIB API:" in captured
    assert "Syncthing:" in captured
