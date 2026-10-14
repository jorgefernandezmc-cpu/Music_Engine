"""
test_sync.py
Unit tests for FileSyncManager: manual moves, ghost cleaner, mass deletion failsafe,
and local file ratings evaluation.
"""

import os
import shutil
import sqlite3
import yaml
from unittest.mock import MagicMock, patch
from src.sync import FileSyncManager
from src.paths import StoragePaths


def test_ghost_cleaner(temp_config, temp_db, temp_env, dummy_playlists):
    paths = StoragePaths(temp_config)
    with open(temp_config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    sync_mgr = FileSyncManager(temp_db, paths, dummy_playlists, cfg)

    # Create 3 physical audio files and records
    conn = sqlite3.connect(temp_db)
    track_ids = ["vid_ghost_1", "vid_ghost_2", "vid_ghost_3"]
    files = []
    for tid in track_ids:
        fpath = os.path.join(temp_env["conveyor_dir"], f"Artist - Track_{tid}.opus")
        lrcpath = os.path.join(temp_env["conveyor_dir"], f"Artist - Track_{tid}.lrc")
        with open(fpath, "wb") as f:
            f.write(b"audio")
        with open(lrcpath, "w", encoding="utf-8") as f:
            f.write("[00:01.00] lyrics")
        files.append((fpath, lrcpath))

        conn.execute(
            "INSERT INTO tracks (id, title, artist, status, is_permanent, file_path) VALUES (?, ?, ?, 'CINTA', 0, ?)",
            (tid, f"Track_{tid}", "Artist", fpath),
        )
    conn.commit()
    conn.close()

    # Delete physical audio of track 1
    os.remove(files[0][0])

    purged_count = sync_mgr.clean_ghost_tracks()
    assert purged_count == 1

    conn = sqlite3.connect(temp_db)
    cur = conn.cursor()
    cur.execute("SELECT status FROM tracks WHERE id = 'vid_ghost_1'")
    assert cur.fetchone()[0] == "PURGED"

    cur.execute("SELECT status FROM tracks WHERE id = 'vid_ghost_2'")
    assert cur.fetchone()[0] == "CINTA"
    conn.close()

    # Verify companion .lrc was removed as well
    assert not os.path.exists(files[0][1])


def test_mass_deletion_failsafe(temp_config, temp_db, temp_env, dummy_playlists):
    paths = StoragePaths(temp_config)
    with open(temp_config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # Set failsafe limit to 5
    cfg["storage"]["mass_deletion_failsafe_limit"] = 5
    sync_mgr = FileSyncManager(temp_db, paths, dummy_playlists, cfg)

    conn = sqlite3.connect(temp_db)
    # Insert 10 tracks whose physical files do NOT exist
    for i in range(10):
        dummy_path = os.path.join(temp_env["conveyor_dir"], f"NonExistent_{i}.opus")
        conn.execute(
            "INSERT INTO tracks (id, title, artist, status, is_permanent, file_path) VALUES (?, ?, ?, 'CINTA', 0, ?)",
            (f"missing_{i}", f"Title_{i}", "Artist", dummy_path),
        )
    conn.commit()
    conn.close()

    # Run ghost cleaner: should abort due to mass deletion limit
    ghosts = sync_mgr.clean_ghost_tracks()
    assert ghosts == 0

    conn = sqlite3.connect(temp_db)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM tracks WHERE status = 'CINTA'")
    assert cur.fetchone()[0] == 10
    conn.close()


def test_sync_manual_moves(temp_config, temp_db, temp_env, dummy_playlists):
    paths = StoragePaths(temp_config)
    with open(temp_config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    sync_mgr = FileSyncManager(temp_db, paths, dummy_playlists, cfg)

    # Track initially in Album_A
    album_a_dir = os.path.join(temp_env["permanent_dir"], "Artist", "Album_A")
    album_b_dir = os.path.join(temp_env["permanent_dir"], "Artist", "Album_B")
    os.makedirs(album_a_dir, exist_ok=True)
    os.makedirs(album_b_dir, exist_ok=True)

    filename = "Artist - Test Track.opus"
    old_path = os.path.join(album_a_dir, filename)
    new_path = os.path.join(album_b_dir, filename)

    with open(old_path, "wb") as f:
        f.write(b"opus")

    conn = sqlite3.connect(temp_db)
    conn.execute(
        "INSERT INTO tracks (id, title, artist, album, status, is_permanent, file_path) VALUES ('id_move', 'Test Track', 'Artist', 'Album_A', 'PERMANENT', 1, ?)",
        (old_path,),
    )
    conn.commit()
    conn.close()

    # User manually moves file to Album_B
    shutil.move(old_path, new_path)

    updated = sync_mgr.sync_manual_moves()
    assert updated == 1

    conn = sqlite3.connect(temp_db)
    cur = conn.cursor()
    cur.execute("SELECT album, file_path FROM tracks WHERE id = 'id_move'")
    row = cur.fetchone()
    assert row[0] == "Album_B"
    assert row[1] == os.path.abspath(new_path)
    conn.close()


def test_local_file_ratings_promotion(temp_config, temp_db, temp_env, dummy_playlists):
    paths = StoragePaths(temp_config)
    with open(temp_config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    sync_mgr = FileSyncManager(temp_db, paths, dummy_playlists, cfg)

    # Place a track in Cravings with collaboration in artist name
    artist_full = "Anther feat. Dib"
    album = "Singles"
    title = "Nuestro Primer Baile"
    craving_folder = os.path.join(temp_env["cravings_dir"], "Anther", "Singles")
    os.makedirs(craving_folder, exist_ok=True)

    audio_path = os.path.join(craving_folder, f"{artist_full} - {title}.opus")
    lrc_path = os.path.join(craving_folder, f"{artist_full} - {title}.lrc")

    with open(audio_path, "wb") as f:
        f.write(b"opus_data")
    with open(lrc_path, "w", encoding="utf-8") as f:
        f.write("[00:05.00] Lyrcs here")

    conn = sqlite3.connect(temp_db)
    conn.execute(
        "INSERT INTO tracks (id, title, artist, album, status, is_permanent, file_path) VALUES ('rate_id_1', ?, ?, ?, 'ANTOJO', 0, ?)",
        (title, artist_full, album, audio_path),
    )
    conn.commit()
    conn.close()

    # Mock mutagen.File returning rating 5
    mock_tags = {
        "RATING": ["5"],
        "artist": [artist_full],
        "title": [title],
        "album": [album],
    }
    mock_obj = MagicMock()
    mock_obj.__contains__.side_effect = lambda k: k in mock_tags
    mock_obj.__getitem__.side_effect = lambda k: mock_tags[k]
    mock_obj.__delitem__.side_effect = lambda k: mock_tags.pop(k, None)

    with patch("mutagen.File", return_value=mock_obj):
        sync_mgr.process_local_file_ratings()

    # Expected location under primary artist "Anther"
    expected_perm_dir = os.path.join(temp_env["permanent_dir"], "Anther", "Singles")
    expected_audio = os.path.join(expected_perm_dir, f"Anther - {title}.opus")
    expected_lrc = os.path.join(expected_perm_dir, f"Anther - {title}.lrc")

    assert os.path.exists(expected_audio)
    assert os.path.exists(expected_lrc)
    assert not os.path.exists(audio_path)
    assert not os.path.exists(lrc_path)

    conn = sqlite3.connect(temp_db)
    cur = conn.cursor()
    cur.execute("SELECT status, is_permanent, file_path FROM tracks WHERE id = 'rate_id_1'")
    row = cur.fetchone()
    conn.close()

    assert row[0] == "PERMANENT"
    assert row[1] == 1
    assert row[2] == expected_audio
