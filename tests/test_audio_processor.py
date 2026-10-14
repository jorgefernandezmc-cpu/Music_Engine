"""
test_audio_processor.py
Unit tests for ReplayGain and EBU R128 loudness normalization (TASK-06).
"""

import os
import subprocess
import hashlib
import pytest
from mutagen.oggopus import OggOpus
from mutagen.mp4 import MP4
from src.audio_processor import (
    calculate_r128_gain,
    apply_replaygain_tags,
    calculate_and_apply_gain,
    has_replaygain_tags,
    normalize_library_audio
)
from src.db import get_db_connection


def _create_test_opus(target_path: str, duration: int = 1):
    """Generates a valid test Opus audio file using ffmpeg."""
    subprocess.run([
        "ffmpeg", "-y", "-nostats", "-loglevel", "error",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-c:a", "libopus", target_path
    ], check=True)


def _create_test_m4a(target_path: str, duration: int = 1):
    """Generates a valid test AAC/M4A audio file using ffmpeg."""
    subprocess.run([
        "ffmpeg", "-y", "-nostats", "-loglevel", "error",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-c:a", "aac", target_path
    ], check=True)


def _get_pcm_checksum(file_path: str) -> str:
    """Decodes raw audio PCM stream and returns its SHA-256 digest."""
    proc = subprocess.run([
        "ffmpeg", "-nostats", "-loglevel", "error",
        "-i", file_path, "-f", "s16le", "-"
    ], stdout=subprocess.PIPE, check=True)
    return hashlib.sha256(proc.stdout).hexdigest()


def test_calculate_and_apply_gain_opus(tmp_path):
    """
    Acceptance Criterion 1 & 2:
    Inspect tags on .opus file and verify PCM audio payload is byte-for-byte identical.
    """
    audio_file = str(tmp_path / "test_track.opus")
    _create_test_opus(audio_file)

    # Compute raw PCM digest before tagging
    pcm_before = _get_pcm_checksum(audio_file)

    # Calculate and apply gain
    success = calculate_and_apply_gain(audio_file, target_lufs=-18.0)
    assert success is True

    # 1. Tag Inspection
    audio = OggOpus(audio_file)
    tags = dict(audio)
    assert "replaygain_track_gain" in tags
    assert "replaygain_track_peak" in tags
    assert "r128_track_gain" in tags
    assert tags["replaygain_track_gain"][0].endswith("dB")

    # 2. Audio Byte Integrity (No generational transcoding loss)
    pcm_after = _get_pcm_checksum(audio_file)
    assert pcm_before == pcm_after

    # Verify has_replaygain_tags helper
    assert has_replaygain_tags(audio_file) is True


def test_calculate_and_apply_gain_m4a(tmp_path):
    """
    Verifies ReplayGain tags application and PCM integrity on .m4a files.
    """
    audio_file = str(tmp_path / "test_track.m4a")
    _create_test_m4a(audio_file)

    pcm_before = _get_pcm_checksum(audio_file)

    success = calculate_and_apply_gain(audio_file, target_lufs=-18.0)
    assert success is True

    audio = MP4(audio_file)
    assert "----:com.apple.iTunes:replaygain_track_gain" in audio
    assert "----:com.apple.iTunes:replaygain_track_peak" in audio

    pcm_after = _get_pcm_checksum(audio_file)
    assert pcm_before == pcm_after
    assert has_replaygain_tags(audio_file) is True


def test_normalize_library_audio_batch(temp_db, temp_config, tmp_path):
    """
    Verifies batch normalization over database tracks with deduplication/skipping.
    """
    file1 = str(tmp_path / "song1.opus")
    file2 = str(tmp_path / "song2.opus")
    _create_test_opus(file1)
    _create_test_opus(file2)

    with get_db_connection(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tracks (id, title, artist, status, file_path)
            VALUES ('s1', 'Song 1', 'Artist 1', 'CINTA', ?)
        """, (file1,))
        cursor.execute("""
            INSERT INTO tracks (id, title, artist, status, file_path)
            VALUES ('s2', 'Song 2', 'Artist 2', 'PERMANENT', ?)
        """, (file2,))
        conn.commit()

    # First pass: normalizes both tracks
    stats1 = normalize_library_audio(db_path=temp_db, config_path=temp_config, limit=50, force=False)
    assert stats1["processed"] == 2
    assert stats1["tagged"] == 2
    assert stats1["skipped"] == 0

    # Second pass: skips both because tags already exist
    stats2 = normalize_library_audio(db_path=temp_db, config_path=temp_config, limit=50, force=False)
    assert stats2["processed"] == 2
    assert stats2["tagged"] == 0
    assert stats2["skipped"] == 2

    # Third pass with force=True: retags both
    stats3 = normalize_library_audio(db_path=temp_db, config_path=temp_config, limit=50, force=True)
    assert stats3["processed"] == 2
    assert stats3["tagged"] == 2
    assert stats3["skipped"] == 0
