"""
test_backup_manager.py
Unit tests for BackupManager: snapshot creation, tar.gz bundle integrity,
hash-based deduplication, and cross-machine path rebasing restore.
"""

import os
import tarfile
import sqlite3
from src.backup_manager import BackupManager
from src.paths import StoragePaths


def test_create_snapshot_bundle(temp_config, temp_db, temp_env):
    paths = StoragePaths(temp_config)
    bm = BackupManager(temp_db, paths)

    # Insert sample data into temp_db
    conn = sqlite3.connect(temp_db)
    conn.execute(
        "INSERT INTO tracks (id, title, artist, status, is_permanent, file_path) VALUES ('b1', 'Song A', 'Artist A', 'PERMANENT', 1, '/old/path/song.opus')"
    )
    conn.commit()
    conn.close()

    # Create snapshot
    backup_file = bm.create_snapshot(tag="test_bundle", force=True)
    assert backup_file is not None
    assert os.path.exists(backup_file)
    assert backup_file.endswith(".tar.gz")

    # Verify bundle structure
    with tarfile.open(backup_file, "r:gz") as tar:
        names = tar.getnames()
        assert "conveyor_state.sqlite" in names
        assert "manifest.json" in names


def test_hash_deduplication(temp_config, temp_db, temp_env):
    paths = StoragePaths(temp_config)
    bm = BackupManager(temp_db, paths)

    # First snapshot
    snap1 = bm.create_snapshot(tag="first", force=True)
    assert snap1 is not None

    # Immediate second snapshot without changes: should be deduped (return None)
    snap2 = bm.create_snapshot(tag="second", force=False)
    assert snap2 is None

    # Forced snapshot should bypass deduplication
    snap3 = bm.create_snapshot(tag="third", force=True)
    assert snap3 is not None


def test_restore_rebase(temp_config, temp_db, temp_env):
    paths = StoragePaths(temp_config)
    bm = BackupManager(temp_db, paths)

    # Setup database with a path belonging to the source environment base_dir
    old_base = paths.base_dir
    old_path = f"{old_base}/Permanent/Artist/Album/Artist - Track.opus"

    conn = sqlite3.connect(temp_db)
    conn.execute(
        "INSERT INTO tracks (id, title, artist, status, is_permanent, file_path) VALUES ('rebase_1', 'Track', 'Artist', 'PERMANENT', 1, ?)",
        (old_path,),
    )
    conn.commit()
    conn.close()

    # Export bundle
    bundle_path = bm.export_full_bundle(output_path=os.path.join(temp_env["backups_dir"], "migration.tar.gz"))
    assert os.path.exists(bundle_path)

    # Restore with path rebasing to new base
    new_base = "/home/newuser/Music"
    restore_summary = bm.restore_backup(
        backup_source=bundle_path,
        target_base_dir=new_base,
        rebase_paths=True,
    )

    assert restore_summary["total_tracks"] >= 1
    assert restore_summary["rebased_count"] >= 1

    # Verify path in database was rewritten
    conn = sqlite3.connect(temp_db)
    cur = conn.cursor()
    cur.execute("SELECT file_path FROM tracks WHERE id = 'rebase_1'")
    updated_path = cur.fetchone()[0]
    conn.close()

    assert updated_path.startswith(new_base)
    assert not updated_path.startswith(old_base)
