"""
audio_processor.py
Audio Loudness Normalization using EBU R128 and ReplayGain metadata tags.
Performs non-destructive loudness measurement and embeds standard tags without re-encoding.
"""

import os
import subprocess
import re
import logging

logger = logging.getLogger('audio_processor')
os.makedirs('logs', exist_ok=True)
if not logger.handlers:
    fh = logging.FileHandler('logs/downloader.log')
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(fh)
    logger.setLevel(logging.INFO)


def calculate_r128_gain(file_path: str, target_lufs: float = -18.0) -> tuple[float, float] | None:
    """
    Measures integrated loudness (I) and true peak using ffmpeg ebur128 filter.
    Returns (gain_db, peak_ratio) or None if measurement failed.
    Does NOT modify the audio stream.
    """
    if not os.path.exists(file_path):
        return None

    cmd = [
        "ffmpeg", "-nostats", "-i", file_path,
        "-filter_complex", "ebur128=peak=true",
        "-f", "null", "-"
    ]
    try:
        proc = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, check=True)
        out = proc.stderr

        # Extract Integrated Loudness
        i_match = re.search(r'Integrated loudness:\s+I:\s+([-\d.]+)\s+LUFS', out)
        # Extract True Peak
        peak_match = re.search(r'True peak:\s+Peak:\s+([-\d.]+)\s+dBFS', out)

        if i_match:
            measured_lufs = float(i_match.group(1))
            gain_db = round(target_lufs - measured_lufs, 2)
            peak_dbfs = float(peak_match.group(1)) if peak_match else 0.0
            peak_ratio = round(10 ** (peak_dbfs / 20.0), 6)
            return gain_db, peak_ratio
    except Exception as e:
        logger.warning(f"Failed calculating EBU R128 gain for {file_path}: {e}")
    return None


def apply_replaygain_tags(file_path: str, gain_db: float, peak_ratio: float, target_lufs: float = -18.0) -> bool:
    """
    Embeds non-destructive ReplayGain and EBU R128 loudness tags into audio files.
    Supports .opus, .m4a, .flac, and .mp3 without altering the underlying audio bytes.
    """
    if not os.path.exists(file_path):
        return False

    try:
        if file_path.endswith('.opus'):
            from mutagen.oggopus import OggOpus
            audio = OggOpus(file_path)
            # Standard Vorbis ReplayGain tags
            audio["REPLAYGAIN_TRACK_GAIN"] = [f"{gain_db:+.2f} dB"]
            audio["REPLAYGAIN_TRACK_PEAK"] = [f"{peak_ratio:.6f}"]
            # RFC 7845 native Opus R128 tag (base -23 LUFS)
            r128_offset = int(round((gain_db + (target_lufs - (-23.0))) * 256))
            audio["R128_TRACK_GAIN"] = [str(r128_offset)]
            audio.save()
            return True

        elif file_path.endswith('.m4a'):
            from mutagen.mp4 import MP4
            audio = MP4(file_path)
            audio["----:com.apple.iTunes:replaygain_track_gain"] = [f"{gain_db:+.2f} dB".encode('utf-8')]
            audio["----:com.apple.iTunes:replaygain_track_peak"] = [f"{peak_ratio:.6f}".encode('utf-8')]
            audio.save()
            return True

        elif file_path.endswith('.flac'):
            from mutagen.flac import FLAC
            audio = FLAC(file_path)
            audio["REPLAYGAIN_TRACK_GAIN"] = [f"{gain_db:+.2f} dB"]
            audio["REPLAYGAIN_TRACK_PEAK"] = [f"{peak_ratio:.6f}"]
            audio.save()
            return True

        elif file_path.endswith('.mp3'):
            import mutagen
            from mutagen.id3 import TXXX
            audio = mutagen.File(file_path)
            if hasattr(audio, 'tags') and audio.tags is not None:
                audio.tags.add(TXXX(encoding=3, desc="REPLAYGAIN_TRACK_GAIN", text=f"{gain_db:+.2f} dB"))
                audio.tags.add(TXXX(encoding=3, desc="REPLAYGAIN_TRACK_PEAK", text=f"{peak_ratio:.6f}"))
                audio.save()
                return True

        return False
    except Exception as e:
        logger.warning(f"Failed applying ReplayGain tags to {file_path}: {e}")
        return False


def has_replaygain_tags(file_path: str) -> bool:
    """Checks whether an audio file already contains ReplayGain or R128 tags."""
    if not os.path.exists(file_path):
        return False
    try:
        import mutagen
        audio = mutagen.File(file_path)
        if audio is None:
            return False
        if file_path.endswith('.opus'):
            return "REPLAYGAIN_TRACK_GAIN" in audio or "R128_TRACK_GAIN" in audio
        elif file_path.endswith('.m4a'):
            return "----:com.apple.iTunes:replaygain_track_gain" in audio
        elif file_path.endswith('.flac'):
            return "REPLAYGAIN_TRACK_GAIN" in audio
        elif file_path.endswith('.mp3'):
            return any(k.startswith("TXXX:REPLAYGAIN_TRACK_GAIN") for k in (audio.tags or {}).keys())
        return False
    except Exception:
        return False


def calculate_and_apply_gain(file_path: str, target_lufs: float = -18.0) -> bool:
    """
    Measures loudness via ffmpeg EBU R128 and writes non-destructive tags in one step.
    """
    res = calculate_r128_gain(file_path, target_lufs=target_lufs)
    if not res:
        return False
    gain_db, peak_ratio = res
    return apply_replaygain_tags(file_path, gain_db, peak_ratio, target_lufs=target_lufs)


def normalize_library_audio(db_path: str = "data/conveyor_state.sqlite", config_path: str = "config/config.yaml", limit: int = 50, force: bool = False) -> dict:
    """
    Scans the music library and applies ReplayGain / EBU R128 tags to audio files lacking them.
    """
    target_lufs = -18.0
    if os.path.exists(config_path):
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
            target_lufs = float(cfg.get('downloader', {}).get('target_lufs', -18.0))

    from src.db import get_db_connection

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, artist, title, file_path 
            FROM tracks 
            WHERE status IN ('CINTA', 'PERMANENT', 'ANTOJO') AND file_path IS NOT NULL
        """)
        tracks = cursor.fetchall()

    stats = {
        'total': len(tracks),
        'processed': 0,
        'tagged': 0,
        'skipped': 0,
        'failed': 0
    }

    count = 0
    for t_id, artist, title, file_path in tracks:
        if limit > 0 and count >= limit:
            break

        if not file_path or not os.path.exists(file_path):
            continue

        stats['processed'] += 1

        if not force and has_replaygain_tags(file_path):
            stats['skipped'] += 1
            continue

        ok = calculate_and_apply_gain(file_path, target_lufs=target_lufs)
        if ok:
            stats['tagged'] += 1
            count += 1
            logger.info(f"ReplayGain applied to: {artist} - {title} ({file_path})")
        else:
            stats['failed'] += 1

    return stats
