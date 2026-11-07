import os
import sqlite3
import pytest
from tools.scrobbler.mpris_scrobbler import MprisScrobbler

def test_scrobbler_queue_and_qualification(tmp_path):
    queue_db = str(tmp_path / "test_queue.sqlite")
    cfg_file = str(tmp_path / "config.yaml")

    with open(cfg_file, "w") as f:
        f.write(f"""
scrobbler:
  enabled: true
  min_play_time: 30
  completion_ratio: 0.50
  player_whitelist:
    - "waveflow"
  queue_db: "{queue_db}"
""")

    scrobbler = MprisScrobbler(config_path=cfg_file, db_path=queue_db)
    assert scrobbler.get_pending_count() == 0

    # Enqueue a track
    scrobbler.enqueue_scrobble(
        artist="Test Artist",
        title="Test Song",
        album="Test Album",
        duration_s=200,
        listened_at=1700000000,
        player="waveflow"
    )

    assert scrobbler.get_pending_count() == 1

    # Verify rows in sqlite
    with sqlite3.connect(queue_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT artist, title, album, duration_s, player FROM pending_scrobbles")
        row = cursor.fetchone()
        assert row == ("Test Artist", "Test Song", "Test Album", 200, "waveflow")

    # Whitelist match tests
    assert scrobbler._matches_whitelist("org.mpris.MediaPlayer2.waveflow") is True
    assert scrobbler._matches_whitelist("org.mpris.MediaPlayer2.spotify") is False
