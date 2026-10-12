# 💻 CLI Command Reference

<p align="center">
  <img src="https://img.shields.io/badge/guide-cli_reference-brightgreen?style=for-the-badge&logo=gnubash&logoColor=white" alt="CLI Reference">
  <img src="https://img.shields.io/badge/interface-main.py-blue?style=for-the-badge" alt="Interface main.py">
</p>

All management, curation, enrichment, maintenance, and backup operations in **Music Engine** are executed through the single unified CLI entry point: [`main.py`](../main.py).

---

## 📑 Table of Contents

- [General Command Syntax](#-general-command-syntax)
- [Command Summary Table](#-command-summary-table)
- [Lifecycle & Engine Runs](#lifecycle--engine-runs)
  - [`run`](#1-run)
  - [`status`](#2-status)
- [Importing & Downloading](#importing--downloading)
  - [`import-playlist`](#3-import-playlist)
  - [`download-pending`](#4-download-pending)
- [Metadata, Genres & Lyrics](#metadata-genres--lyrics)
  - [`enrich-lyrics`](#5-enrich-lyrics)
  - [`enrich-genres`](#6-enrich-genres)
  - [`enrich-metadata`](#7-enrich-metadata)
  - [`fix-metadata`](#8-fix-metadata)
  - [`set-album`](#9-set-album)
- [Playlists & Monitoring](#playlists--monitoring)
  - [`update-playlists`](#10-update-playlists)
  - [`watch-folders`](#11-watch-folders)
- [Telemetry](#telemetry)
  - [`sync-telemetry`](#12-sync-telemetry)
- [Backups & Disaster Recovery](#backups--disaster-recovery)
  - [`backup`](#13-backup)
  - [`export-backup`](#14-export-backup)
  - [`restore-backup`](#15-restore-backup)
- [Shortcut Runner Script](#-shortcut-runner-script)

---

## ⌨️ General Command Syntax

```bash
# Using activated virtual environment:
python main.py <command> [options]

# Directly invoking virtual environment binary:
.venv/bin/python main.py <command> [options]
```

---

## 📊 Command Summary Table

| Command | Arguments / Flags | Primary Role |
| :--- | :--- | :--- |
| [`run`](#1-run) | `[--fill]` | Executes complete autonomous lifecycle cycle. |
| [`status`](#2-status) | — | Displays library track counters, status breakdown, and disk usage. |
| [`import-playlist`](#3-import-playlist) | `<URL_or_ID> [--download] [--no-album-search]` | Indexes a YouTube Music playlist directly into Permanent library. |
| [`download-pending`](#4-download-pending) | — | Downloads queued `PENDING` songs without calling AI curator. |
| [`enrich-lyrics`](#5-enrich-lyrics) | `[--limit N] [--all] [--no-upgrade]` | Scans library and downloads missing synchronized lyrics (`.lrc`). |
| [`enrich-genres`](#6-enrich-genres) | `[--limit N] [--all] [--force-all] [--no-ai]` | Classifies music genres via AI and MusicBrainz into tags and database. |
| [`enrich-metadata`](#7-enrich-metadata) | `[--limit N] [--force-all]` | Populates track numbers and release dates across library and tags. |
| [`fix-metadata`](#8-fix-metadata) | `[--use-ai]` | Audits and repairs mismatched versions (karaoke, covers, live). |
| [`set-album`](#9-set-album) | `"<song>" "<new_album>"` | Reassigns a permanent track to an album and moves files on disk. |
| [`update-playlists`](#10-update-playlists) | — | Forces regeneration of all `.m3u8` playlists and Lune backup. |
| [`watch-folders`](#11-watch-folders) | `[--interval SECONDS]` | Watches library folders for manual changes and updates playlists live. |
| [`sync-telemetry`](#12-sync-telemetry) | — | Syncs scrobbles and ❤️ hearts from ListenBrainz without downloading. |
| [`backup`](#13-backup) | `[--tag TAG] [--force] [--list]` | Creates or lists hot deduplicated SQLite snapshots. |
| [`export-backup`](#14-export-backup) | `[-o OUTPUT_PATH]` | Exports a portable `.tar.gz` bundle for cross-machine migration. |
| [`restore-backup`](#15-restore-backup) | `<SOURCE> [--target-base-dir DIR] [--no-rebase]` | Restores state with automatic file path rebasing. |

---

## Lifecycle & Engine Runs

### 1. `run`
Executes one complete pass of the autonomous lifecycle:
1. Daily release radar for favorite artists.
2. Hot database backup.
3. Reverse sync (detects manual moves) and ghost cleaning (cleans deleted files and orphans).
4. ListenBrainz telemetry sync (updates scrobbles and promotes ❤️ loved tracks).
5. Remote mailbox orders from `requests.txt`.
6. Cravings retention purge (tracks exceeding `retention_days`).
7. Conveyor promotion (tracks with $\ge 15$ scrobbles moved to Permanent).
8. Guillotine purge (unplayed tracks past grace period or high skip ratio).
9. Progressive AI curation (Gemini) and audio downloads (`yt-dlp`).
10. Playlist regeneration and desktop notification.

```bash
# Normal periodic run (downloads up to cycle_max_downloads, default 50):
python main.py run

# Full buffer replenishment mode (keeps running until Conveyor buffer is full):
python main.py run --fill
```

---

### 2. `status`
Displays a clean summary of database track states, disk space consumed, and telemetry sync times:

```bash
python main.py status
```

*Example Output:*
```text
=============================================
 CONVEYOR BELT STATUS
=============================================
Base directory:     /home/user/Music/Songs
Tracks in CONVEYOR: 284
PERMANENT tracks:   1120
CRAVINGS tracks:    14
PENDING tracks:     12
PURGED tracks:      95
---------------------------------------------
Disk space used:    14.85 GB
Last scrobble:      2026-10-12T18:42:10
Last LB sync:       2026-10-12T19:00:00
=============================================
```

---

## Importing & Downloading

### 3. `import-playlist`
Imports a YouTube Music playlist directly into the **Permanent** library. By default, it prioritizes canonical studio album versions over standalone singles or music videos.

```bash
# Index playlist into database only (queued as PENDING):
python main.py import-playlist "https://music.youtube.com/playlist?list=PLxxxxxxxx"

# Index and immediately download all tracks:
python main.py import-playlist "PLxxxxxxxx" --download

# Import exactly as listed on YouTube without searching for studio album versions:
python main.py import-playlist "PLxxxxxxxx" --download --no-album-search
```

---

### 4. `download-pending`
Downloads all queued tracks in `PENDING` status. Useful after importing multiple playlists or when you want to execute downloads without invoking AI recommendations.

```bash
python main.py download-pending
```

---

## Metadata, Genres & Lyrics

### 5. `enrich-lyrics`
Scans your local library for missing lyrics and upgrades existing plain text lyrics to synchronized `.lrc` format:

```bash
# Process a batch of up to 50 tracks (default):
python main.py enrich-lyrics

# Process a custom batch of 100 tracks:
python main.py enrich-lyrics --limit 100

# Scan entire library without batch limits:
python main.py enrich-lyrics --all

# Scan missing lyrics only without attempting to upgrade unsynced ones:
python main.py enrich-lyrics --no-upgrade
```

---

### 6. `enrich-genres`
Classifies musical genres with high accuracy using MusicBrainz and Gemini AI, writing Vorbis/MP4 tags and recording them in SQLite:

```bash
# Enrich a batch of 50 tracks pending genres:
python main.py enrich-genres

# Enrich all pending tracks across the library:
python main.py enrich-genres --all

# Force re-analysis of all tracks even if already tagged:
python main.py enrich-genres --all --force-all

# Rely strictly on MusicBrainz / Deezer without using Gemini AI:
python main.py enrich-genres --all --no-ai
```

---

### 7. `enrich-metadata`
Audits and injects official album track numbers (`track_number`) and release dates (`release_date`) from YouTube Music catalog:

```bash
# Enrich up to 50 tracks:
python main.py enrich-metadata --limit 50

# Enrich entire library:
python main.py enrich-metadata --limit 0

# Force re-evaluation of all tracks:
python main.py enrich-metadata --force-all
```

---

### 8. `fix-metadata`
Audits the library for suspicious tracks (karaoke versions, live bootlegs, 8-bit covers, acoustic tributes) and replaces them with official studio album tracks:

```bash
# Heuristic audit and repair:
python main.py fix-metadata

# Audit with Gemini AI as an advanced tiebreaker:
python main.py fix-metadata --use-ai
```

---

### 9. `set-album`
Reassigns a permanent track to a specific album. The engine updates the database, renames and physically moves both audio and `.lrc` files on disk, updates tags, and cleans empty parent directories:

```bash
python main.py set-album "Get Lucky" "Random Access Memories"
python main.py set-album "Pink Floyd Time" "The Dark Side of the Moon"
```

---

## Playlists & Monitoring

### 10. `update-playlists`
Regenerates all `.m3u8` playlists (`Permanent.m3u8`, `Conveyor.m3u8`, `Priority_Discovery.m3u8`, `Live_Rotation.m3u8`, `Cravings.m3u8`, per-artist playlists) and the Lune player JSON backup:

```bash
python main.py update-playlists
```

---

### 11. `watch-folders`
Runs a lightweight filesystem monitor that detects file movements, additions, or manual reorganizations, instantly refreshing playlists in real time:

```bash
# Monitor changes every 5 seconds (default):
python main.py watch-folders

# Check every 2 seconds:
python main.py watch-folders --interval 2
```

---

## Telemetry

### 12. `sync-telemetry`
Connects to the ListenBrainz API to fetch recent scrobbles and ❤️ loved tracks without running the full engine cycle or initiating downloads:

```bash
python main.py sync-telemetry
```

---

## Backups & Disaster Recovery

### 13. `backup`
Creates hot SQLite snapshots using SQLite WAL backup APIs with SHA-256 hash deduplication:

```bash
# Create a snapshot (skipped if state has not changed):
python main.py backup

# Tag the snapshot with a custom label:
python main.py backup --tag "before_large_import"

# Force snapshot creation bypassing hash deduplication:
python main.py backup --force

# List all available snapshots with dates and sizes:
python main.py backup --list
```

---

### 14. `export-backup`
Exports a self-contained portable migration bundle (`.tar.gz`) containing the database, taste profile, download history, folder state, and manifest to easily migrate to another PC:

```bash
# Export to default destination (data/backups/):
python main.py export-backup

# Export to a custom path:
python main.py export-backup -o ~/Desktop/music_engine_migration.tar.gz
```

---

### 15. `restore-backup`
Restores any snapshot or migration bundle. Automatically creates an emergency safety snapshot before touching active data and rebases file paths to match your current system:

```bash
# Restore on the same machine:
python main.py restore-backup data/backups/music_engine_backup_20261012_120000.tar.gz

# Restore on a new computer with a different music directory:
python main.py restore-backup ~/migration.tar.gz --target-base-dir ~/Music/Songs

# Restore without modifying stored file paths:
python main.py restore-backup backup.sqlite --no-rebase
```

---

## ⚡ Shortcut Runner Script

For interactive terminal execution without typing command flags, use the helper script:

```bash
./scripts/update_now.sh
```

---

<p align="center">
  <a href="configuration.md"><b>⬅ Configuration Guide</b></a> • <a href="mailbox-commands.md"><b>Next: Remote Mailbox Commands ➡</b></a>
</p>
