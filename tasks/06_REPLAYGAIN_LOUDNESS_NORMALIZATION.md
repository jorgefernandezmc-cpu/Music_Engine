# TASK-06: Audio Loudness Normalization (ReplayGain / EBU R128)

- **Priority:** P3 (Enhancement / High Value)
- **Target Files:**
  - `src/downloader.py`
  - `src/cli.py`
  - `config/config.yaml.template`
- **Estimated Complexity:** Medium
- **Status:** ✅ Completed

---

## 1. Problem Description & Root Cause Analysis

* **The Problem:** Audio tracks downloaded from YouTube and YouTube Music originate from disparate masters:
  - Classic tracks (1970s–1990s) are often mastered around $-18$ to $-14$ LUFS.
  - Modern urban, pop, and electronic tracks (2020s) are heavily compressed to $-8$ to $-6$ LUFS.
* **User Experience Impact:** When listening to rotating playlists on mobile devices (Lune, Symfonium, Auxio), the user constantly has to manually adjust headphone volume between songs. Sudden volume spikes are jarring and degrade listening comfort.
* **Technical Requirement:** The solution **must NOT re-encode audio lossily** (no generational transcoding loss). Instead, it must compute EBU R128 loudness and embed non-destructive **ReplayGain / R128 metadata tags** into the `.opus` and `.m4a` files. Mobile players (Lune, Retro Music, Symfonium) read these tags natively to equalize playback gain on the fly.

---

## 2. Step-by-Step Implementation Instructions

### Step 1: Loudness Measurement via `ffmpeg` (EBU R128)
Create a helper function in `src/downloader.py` (or a dedicated `src/audio_processor.py`):
```python
def calculate_r128_gain(file_path: str, target_lufs: float = -18.0) -> tuple[float, float] | None:
    """
    Measures integrated loudness (I) and true peak using ffmpeg ebur128 filter.
    Returns (gain_db, peak_ratio) or None if measurement failed.
    Does NOT modify the audio stream.
    """
    import subprocess
    import re

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
```

### Step 2: Embed ReplayGain Tags via Mutagen
Apply tags without altering audio bytes:
* **For `.opus` files (OggOpus):**
  Opus RFC 7845 standardizes `R128_TRACK_GAIN` as an integer offset from $-23$ LUFS ($gain\_db \times 256$):
  ```python
  # Standard Vorbis ReplayGain tags
  audio["REPLAYGAIN_TRACK_GAIN"] = f"{gain_db:+.2f} dB"
  audio["REPLAYGAIN_TRACK_PEAK"] = f"{peak_ratio:.6f}"
  # RFC 7845 native Opus R128 tag (base -23 LUFS)
  r128_offset = int(round((gain_db + (target_lufs - (-23.0))) * 256))
  audio["R128_TRACK_GAIN"] = str(r128_offset)
  ```
* **For `.m4a` files (MP4):**
  ```python
  audio["----:com.apple.iTunes:replaygain_track_gain"] = f"{gain_db:+.2f} dB".encode('utf-8')
  audio["----:com.apple.iTunes:replaygain_track_peak"] = f"{peak_ratio:.6f}".encode('utf-8')
  ```

### Step 3: Integrate into `Downloader` and CLI
1. Add configuration to `config/config.yaml.template`:
   ```yaml
   downloader:
     apply_replaygain: true
     target_lufs: -18.0  # Industry standard for mobile streaming / ReplayGain
   ```
2. Trigger `calculate_and_apply_gain` immediately following successful download and tagging in `download_pending_tracks()`.
3. Add CLI subcommand in `src/cli.py`:
   `python main.py normalize-audio [--all] [--limit 50]` to scan existing library tracks lacking ReplayGain tags.

---

## 3. Verification & Acceptance Criteria

1. **Tag Inspection Test:**
   Run normalization on a test `.opus` file. Inspect tags using `mutagen.File()`.
   Assert `REPLAYGAIN_TRACK_GAIN` and `R128_TRACK_GAIN` are present.
2. **Audio Byte Integrity:**
   Verify that file audio payload is not transcoded (checksum of decoded raw PCM remains identical).
3. **Player Compatibility:**
   Verify that mobile players reading Vorbis tags apply volume equalization accurately.
