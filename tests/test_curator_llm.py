"""
test_curator_llm.py
Unit and integration tests for CuratorLLM Local Radio optimization (TASK-04).
"""

import os
from unittest.mock import MagicMock
import pytest
from src.curator_llm import CuratorLLM
from src.db import get_db_connection


def test_candidate_selection_large_library_limit(temp_db, temp_config):
    """
    Acceptance Criterion 1:
    With a library of 2,000 tracks, verify that candidate selection limits the output
    to at most 130 candidates (100 highest affinity + 30 discovery).
    """
    curator = CuratorLLM(db_path=temp_db, config_path=temp_config)

    dummy_tracks = []
    for i in range(2000):
        dummy_tracks.append({
            "id": f"track_{i}",
            "artist": f"Artist {i}",
            "title": f"Song {i}",
            "genre": "Rock" if i % 2 == 0 else "Pop",
            "file_path": f"/Music/Conveyor/track_{i}.opus",
            "duration_seconds": 180,
            "play_count": i % 10,
        })

    candidates = curator._select_radio_candidates(dummy_tracks, "chill rock")
    assert len(candidates) == 130

    # Also test small library (<= 120 tracks): all tracks must be retained
    small_tracks = dummy_tracks[:45]
    small_candidates = curator._select_radio_candidates(small_tracks, "chill rock")
    assert len(small_candidates) == 45


def test_context_fidelity_genre_prioritization(temp_db, temp_config):
    """
    Acceptance Criterion 2:
    Verify that tracks containing matching genres receive higher affinity scores
    and are prioritized at the top of the candidate list.
    """
    curator = CuratorLLM(db_path=temp_db, config_path=temp_config)

    tracks = []
    # 10 matching Techno tracks
    for i in range(10):
        tracks.append({
            "id": f"techno_{i}",
            "artist": f"DJ {i}",
            "title": f"Track {i}",
            "genre": "Techno / Acid",
            "file_path": f"/path/techno_{i}.opus",
            "duration_seconds": 360,
            "play_count": 0,
        })
    # 190 non-matching Classical/Acoustic tracks
    for i in range(190):
        tracks.append({
            "id": f"other_{i}",
            "artist": f"Orchestra {i}",
            "title": f"Symphony {i}",
            "genre": "Classical",
            "file_path": f"/path/other_{i}.opus",
            "duration_seconds": 400,
            "play_count": 0,
        })

    candidates = curator._select_radio_candidates(tracks, "techno underground")

    # Top 10 candidates must be the 10 Techno tracks
    top_10_ids = {c["id"] for c in candidates[:10]}
    expected_ids = {f"techno_{i}" for i in range(10)}
    assert top_10_ids == expected_ids


def test_generate_local_radio_prompt_enrichment_and_m3u8(temp_db, temp_config, temp_env, monkeypatch):
    """
    Acceptance Criterion 3:
    Verify prompt contains [Genre: ...] and resulting .m3u8 contains standard
    #EXTINF headers with durations and relative file paths.
    """
    # 1. Create real audio placeholder files
    conveyor_dir = temp_env["conveyor_dir"]
    permanent_dir = temp_env["permanent_dir"]

    file1 = os.path.join(conveyor_dir, "Daft Punk - Technologic.opus")
    file2 = os.path.join(permanent_dir, "Kraftwerk - Autobahn.opus")

    with open(file1, "wb") as f:
        f.write(b"dummy audio 1")
    with open(file2, "wb") as f:
        f.write(b"dummy audio 2")

    # 2. Insert into temp_db
    with get_db_connection(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tracks (id, title, artist, album, duration_seconds, status, file_path, genre, play_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("t1", "Technologic", "Daft Punk", "Human After All", 284, "CINTA", file1, "Electronic / French Touch", 12))

        cursor.execute("""
            INSERT INTO tracks (id, title, artist, album, duration_seconds, status, file_path, genre, play_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("t2", "Autobahn", "Kraftwerk", "Autobahn", 300, "PERMANENT", file2, "Electronic / Krautrock", 8))
        conn.commit()

    curator = CuratorLLM(db_path=temp_db, config_path=temp_config)

    # 3. Mock Gemini client
    captured_prompt = []

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.parsed.ids = ["t1", "t2"]

    def mock_generate_content(model, contents, config):
        captured_prompt.append(contents)
        return mock_resp

    mock_client.models.generate_content.side_effect = mock_generate_content
    curator.client = mock_client

    # 4. Execute generate_local_radio
    curator.generate_local_radio("french electronic vibes")

    # Verify prompt enrichment
    assert len(captured_prompt) == 1
    prompt_text = captured_prompt[0]
    assert "[t1] Daft Punk - Technologic [Genre: Electronic / French Touch]" in prompt_text
    assert "[t2] Kraftwerk - Autobahn [Genre: Electronic / Krautrock]" in prompt_text

    # 5. Verify M3U8 file formatting and relative paths
    expected_filename = f"Radio_{curator.sanitize_filename('french electronic vibes')}.m3u8"
    m3u8_path = os.path.join(temp_env["playlists_dir"], expected_filename)
    assert os.path.exists(m3u8_path)


    with open(m3u8_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]

    assert lines[0] == "#EXTM3U"
    assert lines[1] == "#EXTINF:284,Daft Punk - Technologic"
    assert lines[2] == os.path.relpath(file1, temp_env["playlists_dir"])
    assert lines[3] == "#EXTINF:300,Kraftwerk - Autobahn"
    assert lines[4] == os.path.relpath(file2, temp_env["playlists_dir"])


def test_large_library_simulation_prompt_limit(temp_db, temp_config, temp_env):
    """
    Simulates a full DB of 2,000 tracks and verifies the prompt sent to Gemini
    has at most 130 tracks listed.
    """
    with get_db_connection(temp_db) as conn:
        cursor = conn.cursor()
        batch = []
        for i in range(2000):
            batch.append((
                f"sim_{i}",
                f"Song {i}",
                f"Artist {i}",
                "CINTA",
                f"/fake/path/song_{i}.opus",
                "Pop",
                180,
                i % 5
            ))
        cursor.executemany("""
            INSERT INTO tracks (id, title, artist, status, file_path, genre, duration_seconds, play_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, batch)
        conn.commit()

    curator = CuratorLLM(db_path=temp_db, config_path=temp_config)

    captured_prompt = []
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.parsed.ids = []
    mock_client.models.generate_content.side_effect = lambda model, contents, config: (
        captured_prompt.append(contents) or mock_resp
    )
    curator.client = mock_client

    curator.generate_local_radio("summer party")

    assert len(captured_prompt) == 1
    prompt = captured_prompt[0]
    track_lines = [line for line in prompt.splitlines() if line.strip().startswith("[sim_")]
    assert len(track_lines) <= 130
