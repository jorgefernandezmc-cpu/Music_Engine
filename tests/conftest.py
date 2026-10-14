"""
conftest.py
Global PyTest fixtures and environment isolation for Music Engine test suite.
"""

import os
import sqlite3
import yaml
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def temp_env(tmp_path):
    """
    Sets up an isolated filesystem environment mimicking the music collection.
    """
    music_base = tmp_path / "Music"
    conveyor_dir = music_base / "Conveyor"
    permanent_dir = music_base / "Permanent"
    cravings_dir = music_base / "Cravings"
    playlists_dir = music_base / "Playlists"
    user_playlists_dir = playlists_dir / "Listas Propias"
    backups_dir = tmp_path / "backups"

    for d in [conveyor_dir, permanent_dir, cravings_dir, playlists_dir, user_playlists_dir, backups_dir]:
        d.mkdir(parents=True, exist_ok=True)

    requests_file = music_base / "requests.txt"
    requests_file.write_text("# Requests mailbox\n", encoding="utf-8")

    return {
        "base_dir": str(music_base),
        "conveyor_dir": str(conveyor_dir),
        "permanent_dir": str(permanent_dir),
        "cravings_dir": str(cravings_dir),
        "playlists_dir": str(playlists_dir),
        "user_playlists_dir": str(user_playlists_dir),
        "backups_dir": str(backups_dir),
        "requests_file": str(requests_file),
        "root": tmp_path,
    }


@pytest.fixture
def temp_config(temp_env):
    """
    Creates a temporary config.yaml file bound to temp_env paths.
    """
    config_data = {
        "storage": {
            "base_dir": temp_env["base_dir"],
            "conveyor_dir": "Conveyor",
            "permanent_dir": "Permanent",
            "cravings_dir": "Cravings",
            "playlists_dir": "Playlists",
            "requests_file": "requests.txt",
            "mass_deletion_failsafe_limit": 50,
            "max_db_backups": 5,
        },
        "conveyor": {
            "buffer_size": 750,
            "grace_period_days": 150,
            "promotion_play_count": 15,
            "max_skips_before_purge": 5,
            "max_skip_ratio": 0.7,
            "telemetry_safety_margin_days": 7,
            "curation_batch_per_cycle": 20,
        },
        "downloader": {
            "audio_format": "bestaudio/best",
            "preferred_codec": "opus",
            "fallback_codec": "m4a",
            "batch_size": 50,
            "cycle_max_downloads": 50,
        },
        "telemetry": {
            "listenbrainz_url": "https://api.listenbrainz.org/1",
            "fuzzy_threshold": 80,
            "loved_fuzzy_artist_threshold": 80,
            "loved_fuzzy_title_threshold": 85,
            "lookback_days": 30,
        },
        "backup": {
            "auto_backup": True,
            "dir": temp_env["backups_dir"],
            "max_backups": 5,
            "format": "bundle",
            "dedup_by_hash": True,
            "include_aux_files": True,
        },
        "system": {
            "language": "en",
        },
    }

    config_path = temp_env["root"] / "config.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f)

    return str(config_path)


@pytest.fixture
def temp_db(temp_env):
    """
    Initializes a temporary SQLite database using database/schema.sql.
    """
    db_file = temp_env["root"] / "test_conveyor_state.sqlite"
    schema_path = os.path.abspath("database/schema.sql")

    conn = sqlite3.connect(str(db_file))
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()

    return str(db_file)


@pytest.fixture
def dummy_playlists():
    """
    Mock playlist generator to prevent disk I/O in sync/order tests.
    """
    mock = MagicMock()
    mock.update_all_playlists = MagicMock()
    mock.update_permanent_playlists = MagicMock()
    mock.update_cinta_playlists = MagicMock()
    return mock
