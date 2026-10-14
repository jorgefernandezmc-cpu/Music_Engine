"""
test_smart_conveyor_scoring.py
Unit and integration tests for Dynamic Affinity Scoring on Conveyor Lifecycle (TASK-07).
"""

import os
import sqlite3
import pytest
import yaml

from src.db import get_db_connection, ensure_db_indexes
from src.engine import compute_affinity_score, MusicEngine
from src.paths import StoragePaths


def test_compute_affinity_score_base_and_plays():
    """Tests base score and play count scaling capped at +40."""
    # Base track with 0 plays, 0 skips, old track
    score_0 = compute_affinity_score({'play_count': 0, 'skip_count': 0}, days_since_added=30, days_since_last_play=10)
    assert score_0 == 50.0

    # 5 plays (+20) -> 70.0
    score_5 = compute_affinity_score({'play_count': 5, 'skip_count': 0}, days_since_added=30, days_since_last_play=2)
    assert score_5 == 70.0

    # 15 plays (capped at +40) -> 90.0
    score_15 = compute_affinity_score({'play_count': 15, 'skip_count': 0}, days_since_added=30, days_since_last_play=1)
    assert score_15 == 90.0


def test_compute_affinity_score_recent_velocity():
    """Tests that recent velocity (within 14 days) boosts score ahead of rigid play threshold."""
    # 8 plays in last 14 days:
    # Base 50 + min(8*4, 40) [32] + min(8*5, 20) [20] = 102 -> capped at 100.0
    track = {'play_count': 8, 'skip_count': 0}
    score_high_velocity = compute_affinity_score(track, recent_listens_count=8, days_since_added=7, days_since_last_play=1)
    assert score_high_velocity >= 85.0
    assert score_high_velocity == 100.0


def test_compute_affinity_score_skip_penalty_mitigation():
    """Tests that skip penalty is attenuated when track already has established plays."""
    # 0 plays, 2 skips: penalty = 2 * 8.0 * 1.0 = 16.0 -> 50 - 16 = 34.0
    score_unmitigated = compute_affinity_score({'play_count': 0, 'skip_count': 2}, days_since_added=30, days_since_last_play=5)
    assert score_unmitigated == 34.0

    # 10 plays (mitigation = max(0.2, 1.0 - 0.5) = 0.5):
    # Base 50 + 40 (plays) - (2 * 8.0 * 0.5) [8.0] = 82.0
    score_mitigated = compute_affinity_score({'play_count': 10, 'skip_count': 2}, days_since_added=30, days_since_last_play=5)
    assert score_mitigated == 82.0


def test_compute_affinity_score_idle_decay():
    """Tests penalty decay for tracks idle beyond 45 days."""
    # 60 days idle: decay_days = 15, decay = 15 * 0.4 = 6.0
    score_decay = compute_affinity_score({'play_count': 0, 'skip_count': 0}, days_since_added=60, days_since_last_play=60)
    assert score_decay == 44.0

    # 150 days idle: decay_days = 105, 105 * 0.4 = 42.0 (capped at 35.0) -> 50 - 35 = 15.0
    score_max_decay = compute_affinity_score({'play_count': 0, 'skip_count': 0}, days_since_added=150, days_since_last_play=150)
    assert score_max_decay == 15.0


def test_compute_affinity_score_discovery_immunity():
    """Verifies that new tracks (added <= 14 days) are protected by discovery immunity shield."""
    # Track added 3 days ago with 2 skips and 0 plays:
    # Unshielded: 50 - (2 * 8.0) = 34.0
    # Shielded: max(34.0, 45.0) = 45.0
    score_new_skipped = compute_affinity_score({'play_count': 0, 'skip_count': 2}, days_since_added=3, days_since_last_play=3)
    assert score_new_skipped == 45.0

    # Same track after day 14 loses immunity shield:
    score_old_skipped = compute_affinity_score({'play_count': 0, 'skip_count': 2}, days_since_added=20, days_since_last_play=20)
    assert score_old_skipped == 34.0


def test_db_migration_affinity_score_column(tmp_path):
    """Ensures migration transparently adds affinity_score column and index if missing."""
    db_file = str(tmp_path / "legacy_test.sqlite")
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    # Create legacy table without affinity_score
    cursor.execute("""
        CREATE TABLE tracks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            artist TEXT NOT NULL,
            status TEXT NOT NULL,
            is_permanent BOOLEAN DEFAULT 0,
            play_count INTEGER DEFAULT 0,
            skip_count INTEGER DEFAULT 0,
            file_path TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE listen_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id TEXT,
            listened_at DATETIME
        )
    """)
    conn.commit()

    # Verify column does not exist yet
    cursor.execute("PRAGMA table_info(tracks);")
    cols_before = [r[1] for r in cursor.fetchall()]
    assert "affinity_score" not in cols_before

    # Run ensure_db_indexes
    ensure_db_indexes(conn)

    cursor.execute("PRAGMA table_info(tracks);")
    cols_after = [r[1] for r in cursor.fetchall()]
    assert "affinity_score" in cols_after

    # Ensure index was created
    cursor.execute("PRAGMA index_list(tracks);")
    indexes = [r[1] for r in cursor.fetchall()]
    assert "idx_tracks_affinity" in indexes
    conn.close()


def test_engine_lifecycle_smart_scoring_promotion_and_immunity(temp_config, temp_db, temp_env, monkeypatch):
    """
    Tests end-to-end conveyor lifecycle with smart scoring enabled:
    - High velocity track gets promoted to Permanent ahead of 15 plays.
    - New skipped track is shielded by discovery immunity and NOT purged.
    - Old abandoned track with low affinity gets purged.
    """
    paths = StoragePaths(temp_config)
    conn = get_db_connection(temp_db)
    cursor = conn.cursor()
    ensure_db_indexes(conn)

    # 1. Track A: High velocity (8 plays, added 5 days ago, 8 listens in last 14 days) -> Promoted
    file_a = os.path.join(temp_env["conveyor_dir"], "ArtistA - Hit.opus")
    with open(file_a, "wb") as f:
        f.write(b"AUDIO_HIT")
    cursor.execute("""
        INSERT INTO tracks (id, title, artist, album, status, is_permanent, play_count, skip_count, file_path, added_at, last_played_at)
        VALUES ('t_a', 'Hit', 'ArtistA', 'Singles', 'CINTA', 0, 8, 0, ?, datetime('now', '-5 days'), datetime('now', '-1 days'))
    """, (file_a,))
    # Add 8 listen events in last 14 days
    for i in range(8):
        cursor.execute("INSERT INTO listen_events (track_id, listened_at, source) VALUES ('t_a', datetime('now', '-2 days'), 'ListenBrainz')")

    # 2. Track B: New track with skips (0 plays, 2 skips, added 3 days ago) -> Immune, NOT purged
    file_b = os.path.join(temp_env["conveyor_dir"], "ArtistB - NewSkip.opus")
    with open(file_b, "wb") as f:
        f.write(b"AUDIO_NEW_SKIP")
    cursor.execute("""
        INSERT INTO tracks (id, title, artist, album, status, is_permanent, play_count, skip_count, file_path, added_at, last_played_at)
        VALUES ('t_b', 'NewSkip', 'ArtistB', 'Singles', 'CINTA', 0, 0, 2, ?, datetime('now', '-3 days'), datetime('now', '-3 days'))
    """, (file_b,))

    # 3. Track C: Stale skipped track (0 plays, 5 skips, added 30 days ago, idle 30 days) -> Purged
    file_c = os.path.join(temp_env["conveyor_dir"], "ArtistC - Stale.opus")
    with open(file_c, "wb") as f:
        f.write(b"AUDIO_STALE")
    cursor.execute("""
        INSERT INTO tracks (id, title, artist, album, status, is_permanent, play_count, skip_count, file_path, added_at, last_played_at)
        VALUES ('t_c', 'Stale', 'ArtistC', 'Singles', 'CINTA', 0, 0, 5, ?, datetime('now', '-30 days'), datetime('now', '-30 days'))
    """, (file_c,))

    conn.commit()
    conn.close()

    # Mock engine dependencies to isolate lifecycle test
    engine = MusicEngine(db_path=temp_db, config_path=temp_config)
    monkeypatch.setattr(engine.telemetry, "is_telemetry_fresh", lambda: True)
    monkeypatch.setattr(engine.telemetry, "process_listens", lambda: (0, 0))
    monkeypatch.setattr(engine.telemetry, "get_loved_tracks", lambda: [])
    monkeypatch.setattr(engine.curator, "run_curation_cycle", lambda n: 0)
    monkeypatch.setattr(engine.downloader, "download_pending_tracks", lambda: 0)
    monkeypatch.setattr(engine.order_processor, "process_peticiones", lambda: 0)
    monkeypatch.setattr(engine, "_check_release_radar", lambda: None)
    monkeypatch.setattr(engine, "_check_daily_lyrics_scan", lambda: None)
    monkeypatch.setattr(engine, "_check_daily_genre_scan", lambda: None)

    # Run lifecycle cycle
    engine.run(fill_mode=False)

    conn = get_db_connection(temp_db)
    cursor = conn.cursor()

    # Track A should be promoted to PERMANENT
    cursor.execute("SELECT status, is_permanent, affinity_score FROM tracks WHERE id = 't_a'")
    row_a = cursor.fetchone()
    assert row_a[0] == "PERMANENT"
    assert row_a[1] == 1
    assert row_a[2] >= 85.0

    # Track B should still be CINTA (immune from purge)
    cursor.execute("SELECT status, affinity_score FROM tracks WHERE id = 't_b'")
    row_b = cursor.fetchone()
    assert row_b[0] == "CINTA"
    assert row_b[1] == 45.0  # Protected at 45.0 by immunity shield
    assert os.path.exists(file_b)

    # Track C should be PURGED (affinity <= 15.0 and added > 14 days)
    cursor.execute("SELECT status, affinity_score FROM tracks WHERE id = 't_c'")
    row_c = cursor.fetchone()
    assert row_c[0] == "PURGED"
    assert row_c[1] <= 15.0
    assert not os.path.exists(file_c)

    conn.close()


def test_engine_lifecycle_fallback_when_disabled(temp_config, temp_db, temp_env, monkeypatch):
    """Verifies fallback to legacy binary count rules when smart_scoring: false."""
    with open(temp_config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["conveyor"]["smart_scoring"] = False
    with open(temp_config, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f)

    conn = get_db_connection(temp_db)
    cursor = conn.cursor()
    ensure_db_indexes(conn)

    # Track with 8 plays (affinity would promote, but legacy needs 15 plays)
    file_p = os.path.join(temp_env["conveyor_dir"], "ArtistP - EightPlays.opus")
    with open(file_p, "wb") as f:
        f.write(b"AUDIO")
    cursor.execute("""
        INSERT INTO tracks (id, title, artist, album, status, is_permanent, play_count, skip_count, file_path, added_at, last_played_at)
        VALUES ('t_p', 'EightPlays', 'ArtistP', 'Singles', 'CINTA', 0, 8, 0, ?, datetime('now', '-5 days'), datetime('now', '-1 days'))
    """, (file_p,))
    conn.commit()
    conn.close()

    engine = MusicEngine(db_path=temp_db, config_path=temp_config)
    monkeypatch.setattr(engine.telemetry, "is_telemetry_fresh", lambda: True)
    monkeypatch.setattr(engine.telemetry, "process_listens", lambda: (0, 0))
    monkeypatch.setattr(engine.telemetry, "get_loved_tracks", lambda: [])
    monkeypatch.setattr(engine.curator, "run_curation_cycle", lambda n: 0)
    monkeypatch.setattr(engine.downloader, "download_pending_tracks", lambda: 0)
    monkeypatch.setattr(engine.order_processor, "process_peticiones", lambda: 0)
    monkeypatch.setattr(engine, "_check_release_radar", lambda: None)
    monkeypatch.setattr(engine, "_check_daily_lyrics_scan", lambda: None)
    monkeypatch.setattr(engine, "_check_daily_genre_scan", lambda: None)

    engine.run(fill_mode=False)

    conn = get_db_connection(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM tracks WHERE id = 't_p'")
    status = cursor.fetchone()[0]
    # Under legacy rules, 8 plays < 15, so it remains in CINTA
    assert status == "CINTA"
    conn.close()
