"""
test_order_processor.py
Unit tests for OrderProcessor: mailbox parsing, URL extractions, album moves,
and mailbox cleaning.
"""

import os
import sqlite3
from src.order_processor import OrderProcessor, extract_url_info
from src.paths import StoragePaths


def test_extract_url_info():
    # YouTube video formats
    yt1 = extract_url_info("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert yt1 == {"provider": "youtube", "type": "video", "id": "dQw4w9WgXcQ", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}

    yt_short = extract_url_info("https://youtu.be/dQw4w9WgXcQ?t=10")
    assert yt_short["provider"] == "youtube"
    assert yt_short["type"] == "video"
    assert yt_short["id"] == "dQw4w9WgXcQ"

    yt_shorts = extract_url_info("https://www.youtube.com/shorts/dQw4w9WgXcQ")
    assert yt_shorts["id"] == "dQw4w9WgXcQ"

    # YouTube playlist
    yt_pl = extract_url_info("https://www.youtube.com/playlist?list=PL123456789")
    assert yt_pl["provider"] == "youtube"
    assert yt_pl["type"] == "playlist"
    assert yt_pl["id"] == "PL123456789"

    # Spotify URLs
    sp_track = extract_url_info("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT?si=abc")
    assert sp_track["provider"] == "spotify"
    assert sp_track["type"] == "track"
    assert sp_track["id"] == "4cOdK2wGLETKBW3PvgPWqT"

    sp_album = extract_url_info("https://open.spotify.com/album/2noRn2Aes5aoNVsU6iWThc")
    assert sp_album["provider"] == "spotify"
    assert sp_album["type"] == "album"
    assert sp_album["id"] == "2noRn2Aes5aoNVsU6iWThc"

    # Invalid / unsupported
    assert extract_url_info("not a url") is None
    assert extract_url_info("https://example.com/audio.mp3") is None


def test_clean_peticiones_file(temp_config, temp_env):
    paths = StoragePaths(temp_config)
    proc = OrderProcessor("dummy.sqlite", temp_config, paths=paths)

    header_lines = ["# Mailbox Header Line 1\n", "# Mailbox Header Line 2\n"]
    failed = ['album: Bad Track -> NewAlbum  # ERROR: Track not found\n']
    info = ['# [INFO] Artist - Title | Album: Singles | Status: PERMANENT\n']

    req_file = paths.requests_file
    proc.clean_peticiones_file(req_file, header_lines, failed_lines=failed, info_lines=info)

    with open(req_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "# Mailbox Header Line 1" in content
    assert "Bad Track" in content
    assert "ERROR: Track not found" in content
    assert "[INFO] Artist - Title" in content


def test_process_album_move(temp_config, temp_db, temp_env, dummy_playlists):
    paths = StoragePaths(temp_config)
    proc = OrderProcessor(temp_db, temp_config, paths=paths, playlists=dummy_playlists)

    # Insert an existing permanent track
    old_album_dir = os.path.join(temp_env["permanent_dir"], "Quevedo", "Singles")
    os.makedirs(old_album_dir, exist_ok=True)
    old_audio = os.path.join(old_album_dir, "Quevedo - Columbia.opus")
    old_lrc = os.path.join(old_album_dir, "Quevedo - Columbia.lrc")
    with open(old_audio, "wb") as f:
        f.write(b"opus")
    with open(old_lrc, "w", encoding="utf-8") as f:
        f.write("[00:01.00] lyrics")

    conn = sqlite3.connect(temp_db)
    conn.execute(
        "INSERT INTO tracks (id, title, artist, album, status, is_permanent, file_path) VALUES ('q_columbia', 'Columbia', 'Quevedo', 'Singles', 'PERMANENT', 1, ?)",
        (old_audio,),
    )
    conn.commit()

    # Move to official album "Donde Quiero Estar"
    ok, msg = proc.process_album_move(conn, "Quevedo - Columbia", "Donde Quiero Estar")
    conn.close()

    assert ok is True
    expected_new_dir = os.path.join(temp_env["permanent_dir"], "Quevedo", "Donde Quiero Estar")
    expected_new_audio = os.path.join(expected_new_dir, "Quevedo - Columbia.opus")
    expected_new_lrc = os.path.join(expected_new_dir, "Quevedo - Columbia.lrc")

    assert os.path.exists(expected_new_audio)
    assert os.path.exists(expected_new_lrc)
    assert not os.path.exists(old_audio)
    assert not os.path.exists(old_lrc)
