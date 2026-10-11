# CONTEXT.md — Music Engine Architecture & Context Document

This document centralizes the full technical, architectural, functional, and operational knowledge of the **Music Engine (The Musical Conveyor Belt)** project. It serves as the single, canonical reference for developers and AI agents maintaining or extending the system.

> [!IMPORTANT]
> ### 🤖 Mandatory Directives for AI Agents & Contributors:
> 1. **Code & Commits in English Only:** All code, class/function names, variables, docstrings, inline comments, log output, and git commit messages must be strictly written in English.
> 2. **Data Privacy & `.gitignore` Enforcement:** Never commit personal user data, runtime databases, cache, audio files, credentials, or private state to Git. If introducing any new state, database, or cache file, you **must** verify and ensure it is properly excluded in `.gitignore`.
> 3. **Documentation Sync:** Whenever changes are made to the code, database schema, CLI options, architecture, or configuration, you **must** update both `CONTEXT.md` and `README.md` to reflect the changes accurately.

---

## 1. Project Overview

**Music Engine** is an autonomous, self-hosted, and 100% private music ecosystem designed to:
1. Maintain a local high-fidelity audio library (`.opus` / `.m4a`).
2. Discover new music automatically using Artificial Intelligence (Google Gemini) and YouTube Music radios.
3. Prioritize **studio album versions** at all times over standalone singles or promotional releases using strict heuristic and semantic analysis.
4. Rigorously organize the permanent collection under the hierarchy:
   `Permanente/<Primary_Artist>/<Album>/<Primary_Artist> - <Title>.opus` (without intermediate discovery or favorites subdirectories).
5. Manage a rotating track buffer ("The Conveyor") with an automated lifecycle: tracks that are enjoyed get promoted to the permanent library; tracks that remain unplayed or get skipped are purged from disk.
6. Process on-demand requests and music management commands via natural language or structured syntax through a synced text file (`peticiones.txt`).
7. Bidirectionally sync files between PC and Android mobile devices using **Syncthing**, backing up code, database, and audio files.
8. Close the feedback loop using offline/online telemetry: the mobile player (**Lune**) emits *scrobbles* via **Pano Scrobbler** to **ListenBrainz**, and the PC engine periodically downloads that history to update play counts and shield tracks marked with a heart ("Love").
9. Supply integrated lyrics: tag injection into Vorbis/ID3 tags and contiguous synchronized `.lrc` sidecar files for universal mobile player compatibility.

---

## 2. System Topology and Data Flow

```
 +-----------------------------------------------------------------------+
 |                            MOBILE DEVICE                              |
 |                                                                       |
 |   [ Local Player ] --------> [ Pano Scrobbler ] ----> [ ListenBrainz ]|
 |       (Lune)                        |                   (Cloud API)   |
 |          ^                          |                        |        |
 +----------|--------------------------|------------------------|--------+
            | (Audio files             | (Heart / Love Feedback)|
            |  & .lrc sidecars)        |                        |
            v                          |                        |
    === [ SYNCTHING ] ===              |                        |
            ^                          |                        |
+-----------|--------------------------|------------------------|--------+
|           v                          v                        v        |
|    Canciones Directory         API Feedback             API Scrobbles  |
|  (/.../Musica/Canciones)             |                        |        |
|           |                          +------------+-----------+        |
|           |                                       |                    |
|           v                                       v                    |
|  +-------------------------------------------------------------+      |
|  |                      MUSIC ENGINE (PC)                      |      |
|  |                                                             |      |
|  |  - StoragePaths     <-- (Configurable paths in config.yaml) |      |
|  |  - AlbumResolver    <-- (Studio album version prioritizer)  |      |
|  |  - TelemetryEngine  <-- (Sync scrobbles, Loved Tracks)      |      |
|  |  - FileSyncManager  <-- (Detects manual moves & ghost files)|      |
|  |  - PurgeEngine      <-- (Grace period & skip guillotine)    |      |
|  |  - CuratorLLM       <-- (Gemini + YTMusic Radio / Requests) |      |
|  |  - Downloader       <-- (yt-dlp + Mutagen + LRCLIB + YTM)   |      |
|  |  - PlaylistGen      <-- (Standard M3U8 & Lune JSON backup)  |      |
|  |                                                             |      |
|  |                     SQLite Database                         |      |
|  |               (data/conveyor_state.sqlite)                  |      |
|  +-------------------------------------------------------------+      |
|                                                                        |
|                               LINUX PC                                 |
|               (Automated via systemd user timer)                       |
+------------------------------------------------------------------------+
```

---

## 3. Project Structure and Directories

The `Music_Engine` repository is structured modularly:

```
Music_Engine/
├── main.py                     # Clean entry point delegating to src.cli
├── requirements.txt            # Python dependencies
├── README.md                   # Quick installation and usage documentation
├── CONTEXT.md                  # This canonical architecture reference
│
├── config/                     # Configuration files and local credentials
│   ├── config.yaml.template    # Base configuration template
│   ├── config.yaml             # Active user configuration (paths, buffers, APIs)
│   ├── headers_auth.json       # YT Music authentication headers (optional)
│   └── cookies.txt             # Exported cookies for age-restricted videos
│
├── database/                   # Database definition and initialization
│   ├── schema.sql              # DDL schema for SQLite tables and indexes
│   └── init_db.py              # Script to initialize data/conveyor_state.sqlite
│
├── data/                       # Local state storage (git-ignored / backed up)
│   ├── conveyor_state.sqlite   # Active SQLite database
│   ├── engine.lock             # Concurrency lock via FileLock
│   ├── taste_profile.json      # Contextual taste profile for Curator LLM
│   ├── download_archive.txt    # yt-dlp historical download archive
│   └── backups/                # Automatic SQLite database backups
│
├── scripts/                    # Helper scripts and runners
│   └── update_now.sh           # Interactive quick runner script
│
├── logs/                       # Execution and audit logs
│   ├── engine.log              # Main engine lifecycle log
│   ├── downloader.log          # yt-dlp and Mutagen tag traces
│   ├── curator.log             # Gemini prompts and evaluations
│   ├── telemetry.log           # ListenBrainz sync and scrobbles
│   └── systemd.log             # Output from systemd service
│
└── src/                        # Modular source code
    ├── __init__.py
    ├── db.py                   # Optimized SQLite connection (WAL, RAM cache, busy timeout)
    ├── sync.py                 # Reverse sync, ghost cleaning, rating tags (FileSyncManager)
    ├── order_processor.py      # peticiones.txt mailbox processor (OrderProcessor)
    ├── notifications.py        # Non-blocking desktop notifications (notify-send)
    ├── paths.py                # Storage path resolution (StoragePaths)
    ├── album_resolver.py       # Heuristic & semantic studio album resolution
    ├── engine.py               # Central lifecycle orchestrator (MusicEngine)
    ├── curator_llm.py          # Gemini AI curation and YTMusic radio recommendations
    ├── downloader.py           # yt-dlp downloader, Mutagen tagging, lyrics injection
    ├── lyrics_provider.py      # Multi-source lyrics cascade (LRCLIB, syncedlyrics, YTM, lyrics.ovh)
    ├── genre_resolver.py       # Accurate multi-tag genre classification (Gemini + MusicBrainz)
    ├── telemetry.py            # ListenBrainz telemetry and scrobble synchronization
    ├── playlist_gen.py         # M3U8 playlist generator with metadata cache and Lune backup
    ├── ytm_extractor.py        # Bulk importer and Spotify/YTM track crossover
    ├── enrich_lyrics.py        # Bulk offline lyrics enricher and validator
    └── cli.py                  # CLI argument parsing and subcommands
```

### Audio Paths (Storage Hierarchy)
The root music directory is configured in `config/config.yaml` (`storage.base_dir`):
- **`Conveyor/` (or `Cinta/`)**: `<Artist> - <Title>.opus` (Ephemeral discovery rotating buffer).
- **`Permanent/` (or `Permanente/`)**: `<Primary_Artist>/<Album>/<Primary_Artist> - <Title>.opus` and `.lrc`.
  - **Strict rule:** No intermediate discovery or favorites subdirectories inside Permanent. Everything is organized strictly by Primary Artist and Album.
- **`Playlists/`**: Core `.m3u8` playlists, subfolder `Playlists/Artistas/` with individual artist playlists, and optional native Lune backup (`lune_playlists_backup.json`).
- **`requests.txt` (or `peticiones.txt`)**: Remote mailbox synced via Syncthing (orders, commands, and track requests).

---

## 4. SQLite Data Model

File location: `data/conveyor_state.sqlite`.
Schema definition: `database/schema.sql`.

### `tracks` Table
Stores the catalog of tracks known to the system:
- `id` (TEXT PRIMARY KEY): YouTube video ID (e.g. `dQw4w9WgXcQ`) or synthesized ID for duplicates (`<vid>_<hex>`).
- `title` (TEXT NOT NULL): Normalized track title.
- `artist` (TEXT NOT NULL): Full artist string with collaborators (used for ID3/Vorbis tags and scrobbling).
- `album` (TEXT): Official album name (prioritized as studio album).
- `duration_seconds` (INTEGER): Duration in seconds.
- `status` (TEXT NOT NULL): Lifecycle state:
  - `PENDING`: Queued for download into `Cinta`, `Permanente`, or `Antojos` (`Cravings`).
  - `CINTA`: Downloaded and active in the ephemeral Conveyor buffer.
  - `PERMANENT`: Part of the permanent, untouchable library.
  - `ANTOJO`: Downloaded and active in the temporary Cravings folder (purged after `retention_days`).
  - `PURGED`: Removed due to grace period expiry, retention expiry, repeated skips, or manual deletion. Never auto-downloaded again.
  - `FAILED`: Download error or transient failure (auto-recoverable to `PENDING`).
- `is_permanent` (BOOLEAN DEFAULT 0): Boolean permanence flag.
- `added_at` (DATETIME DEFAULT CURRENT_TIMESTAMP): Timestamp when added to the system.
- `last_played_at` (DATETIME): Timestamp of last recorded scrobble.
- `play_count` (INTEGER DEFAULT 0): Total recorded play count.
- `skip_count` (INTEGER DEFAULT 0): Cumulative skips without completing a play.
- `file_path` (TEXT): Absolute path to audio file on disk.
- `genre` (TEXT): Assigned musical genre or category.
- `track_number` (INTEGER): Official album track number.
- `release_date` (TEXT): Official release date or year (YYYY-MM-DD or YYYY).

### `listen_events` Table
Chronological listening history:
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT).
- `track_id` (TEXT NOT NULL, FK -> `tracks(id)`).
- `listened_at` (DATETIME NOT NULL): UTC timestamp of the scrobble.
- `source` (TEXT): Event source (typically `listenbrainz`).

### `system_metadata` Table
Key-value configuration and execution state pairs:
- `last_listenbrainz_sync`: UNIX timestamp of last successful ListenBrainz API query.
- `last_radar_check`: UNIX timestamp of last Daily Release Radar check.

### `orphan_scrobbles` Table
Scrobbles from ListenBrainz that didn't match any local track (listened on other devices or external services):
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT).
- `artist` (TEXT), `title` (TEXT).
- `attempts` (INTEGER DEFAULT 0): Retry counter. Purged after exceeding 2 failed attempts.

---

## 5. System Modules and Components

### 5.1. `src/paths.py` (`StoragePaths`)
Resolves all absolute and relative paths based on `config/config.yaml`.
- Provides helper methods to construct clean paths:
  - `get_permanent_track_path(artist, album, title, ext='.opus')`
  - `get_conveyor_track_path(artist, title, ext='.opus')`
  - `get_craving_track_path(artist, album, title, ext='.opus')`
  - Backward-compatible aliases: `get_permanente_track_path`, `get_cinta_track_path`, `get_antojo_track_path`.
  - Properties: `cravings_dir` (alias `antojos_dir`), `conveyor_dir` (`cinta_dir`), `permanent_dir` (`permanente_dir`).

### 5.2. `src/album_resolver.py` (`resolve_album_track`, `get_primary_artist`)
- **Primary artist extraction:**
  - `get_primary_artist`: Extracts the main artist for directory structuring to avoid collisions or huge folder names (e.g., `'Anther, Dib'` -> `'Anther'`, `'3AM feat. Khea'` -> `'3AM'`). Preserves full collaborator lists in metadata for accurate scrobbling.
- **Studio album heuristic resolution:**
  - Distinguishes standalone singles from official studio albums (`is_studio_album`).
  - Strict +100 heuristic score bonus for official album versions with high semantic match.
  - **Antagonistic keyword exclusion filter:** Prevents false positives where different tracks with similar names on the same album got confused (e.g., *"Nuestro Primer Baile"* vs *"Nuestro Último Baile"* by checking antonym pairs like `first`/`last`, `intro`/`outro`, `remix`/`original`).

### 5.3. `src/downloader.py` (`Downloader`)
- Downloads high-quality audio using `yt-dlp` to Opus or M4A.
- **Metadata and tag embedding:**
  - `artist`: Full collaborator list for faithful scrobbling.
  - `albumartist` / `aART`: Primary artist for clean navigation in players.
  - `album`, `title`, `tracknumber`, high-resolution embedded cover art.
- **Dual-source synchronized lyrics:**
  1. *LRCLIB API* (primary source with timestamps and synced text).
  2. *YouTube Music API Fallback* (fetches official lyrics via `get_watch_playlist` and `get_lyrics`).
  - Embeds Vorbis/MP4 tags (`LYRICS`, `SYNCEDLYRICS`, `UNSYNCEDLYRICS`) directly into the audio file.
  - Generates contiguous sidecar `.lrc` file (`<Track>.lrc`) for universal mobile player support.

### 5.4. `src/engine.py` (`MusicEngine`)
Central orchestrator of the music lifecycle.
- **Concurrency lock:** `FileLock('data/engine.lock')`.
- **Lifecycle execution flow (`run`):**
  1. **Release Radar:** Scans for recent releases from favorite artists.
  2. **Auto-Backup:** Generates SQLite backups in `data/backups/`.
  3. **Reverse Sync:** Detects manual file moves to `Permanente` and updates database records.
  4. **Ghost Cleaner:** Detects manual deletions from mobile/PC, immediately cleans associated `.lrc` sidecars, purges orphan `.lrc` files without audio, and marks tracks as `PURGED` (with a 50-file mass-deletion failsafe; covers `CINTA`, `PERMANENT`, and `ANTOJO`).
  5. **ListenBrainz Telemetry:** Downloads recent scrobbles and updates `play_count` and timestamps.
  6. **Heart Shielding ("Love"):** Tracks hearted on mobile immediately transition to `PERMANENT` and are moved to their official artist/album folder.
  7. **Requests Mailbox & Remote Commands (`peticiones.txt` / `requests.txt`):**
     - Maintains a persistent header with a quick command guide.
     - **Permanent Single Track:** `Download "Song" by Artist` or `permanent: <Artist> - <Title>`.
     - **Craving Single Track (Temporary):** `craving: <Artist> - <Title>` or `antojo: <Artist> - <Title>` (downloads directly into Cravings folder).
     - **Full Permanent Album:** `album: <Artist> - <Album>` or `permanent album: <Artist> - <Album>` (downloads complete official tracklist to Permanent).
     - **Full Craving Album (Temporary):** `craving album: <Artist> - <Album>` or `antojo album: <Artist> - <Album>` (downloads complete official tracklist to Cravings).
     - **Genre Correction:** `genre: <track> -> <new_genre>` (or `genre: <track>` for automatic AI re-analysis; updates SQLite and physical tags).
     - **Lyrics Refresh:** `lyrics: <track>` (forces re-scan and clean download of synced `.lrc` lyrics).
     - **Promote to Permanent:** `favorite: <track>` / `permanent: <track>` (moves from Conveyor or Cravings to Permanent album folder immediately).
     - **Purge Track:** `purge: <track>` / `delete: <track>` (removes from Conveyor or Cravings and cleans audio + `.lrc`).
     - **Album Reassignment:** `album: <track> -> <new_album>` (moves audio and `.lrc`, updates tags, cleans old directories).
     - **Self-Repair:** `fix: <track>` (downloads verified official version).
     - **Local Radios:** `radio: <vibe>`.
     - **Direct Permanent Requests:** Downloads by song, artist, or style directly into the permanent library via AI Curator.
     - **Feedback Loop:** Successfully processed commands are cleared from the file; failed commands are retained with an explanation comment.
  8. **Strict Duplicate Prevention in Conveyor:** Conveyor never downloads tracks already in `Permanente` (both by YouTube ID and normalized title/artist match).
  9. **Cravings Retention & Auto-Purge (`_purge_cravings`):** Tracks in Cravings (`ANTOJO` status) are automatically purged after exceeding configured `cravings.retention_days` (default 30 days without play), removing physical audio files, `.lrc` sidecars, empty directories, and updating status to `PURGED`.
  10. **Automatic Promotion:** Tracks with sufficient plays (>=15) are promoted from Conveyor to `Permanente`.
  11. **Guillotine Purge:** Unplayed Conveyor tracks past the grace period or with high skip ratios are physically deleted and marked `PURGED`.
  12. **Progressive Buffer Replenishment:**
      - In periodic automated cycles: moderate curation (up to 20 tracks) and limited batch downloads (up to 50 tracks) to avoid bandwidth saturation or rate limits.
      - In full manual mode (`--fill`): fills all open slots up to maximum buffer capacity (750 tracks).
  13. **Auto-Recovery:** Automatically resets `FAILED` tracks to `PENDING` on the next run for retry.
  14. **Playlist Regeneration:** Regenerates all `.m3u8` playlists (including `Antojos.m3u8` / `Cravings.m3u8`) and the Lune JSON backup.
  15. **Consolidated Desktop Notifications:** No per-song spam. Emits a single grouped notification after lyrics batches (with expandable track breakdown) and an execution summary at the end of the engine run.

### 5.5. `src/telemetry.py` (`TelemetryEngine`)
- Connects to the ListenBrainz API to retrieve scrobble history and "Loved Tracks".
- Cross-references IDs and fuzzy metadata with local database to match plays with high accuracy.

### 5.6. `src/curator_llm.py` (`CuratorLLM`)
- Integrates Google GenAI SDK (Gemini) to evaluate track recommendations based on taste profile (`data/taste_profile.json`).
- Extracts candidate tracks from YouTube Music radios and filters out known or redundant songs.

### 5.7. `src/playlist_gen.py` (`PlaylistGenerator`)
Generates playlists with a dual strategy (universal M3U8 + native Lune JSON backup) and reactive directory modification detection:
- **Universal M3U8 Playlists:** Standard `#EXTM3U` and `#EXTINF` directives with exact durations and relative paths:
  - `Permanente.m3u8`: Complete permanent collection organized alphabetically by Artist -> Album -> Track.
  - `Cinta.m3u8`: All tracks currently rotating in the Conveyor buffer.
  - `Descubrimiento_Prioritario.m3u8`: New Conveyor tracks awaiting first play (`play_count = 0`).
  - `Rotación_Viva.m3u8`: Dynamic smart playlist (top played + related discoveries + forgotten gems).
  - Individual Artist Playlists in `Playlists/Artistas/<Artist>.m3u8`: Inclusive and collaborative (tracks where artist is primary or featured). Filtered by configurable threshold (`playlists.min_artist_tracks`, default 10).
- **Reactive Folder Change Detection:**
  - Fast fingerprinting (<15 ms) using audio file counts, `mtime_ns`, and sizes (`data/playlist_folder_state.json`).
  - `update_permanent_playlists`: Regenerates `Permanente.m3u8` and artist playlists when `Permanente` changes.
  - `update_cinta_playlists`: Regenerates `Cinta.m3u8` and `Descubrimiento_Prioritario.m3u8` when `Cinta` changes.
  - Integrated into all engine operations (promotions, purges, downloads, manual moves, hearts, and mailbox commands).
- **Native Lune Backup (`lune_playlists_backup.json`):** Generates version 2 JSON backup required by Lune's native importer (`PlaylistBackupManager.kt`).
  - Includes key playlists: `Permanente`, `Cinta`, `Descubrimiento Prioritario`, `Rotación Viva`, plus eligible artist playlists.
  - **Tag Fidelity & Millisecond Precision:** Reads `title` and `artist` directly from physical Vorbis/ID3 tags with Mutagen and computes exact duration in milliseconds (`dur_ms`). Synced automatically via Syncthing.

---

## 6. Synchronization & Mobile Ecosystem

### P2P Sync (Syncthing)
- Shared folder: `~/Music` (or configured `storage.base_dir`).
- Exclusion configuration (`.stignore` at the root of Music folder):
  ```
  (?d).venv*
  (?d)__pycache__
  (?d)*.pyc
  (?d)*.lock
  ```
- Ensures tracks, `.lrc` lyrics, database, and code scripts remain in sync without transferring transient runtime locks or virtual environments.

### Mobile Player & Compatibility
- **Lune (Android):** Modern lightweight offline music player:
  - Organizes and plays via folders, artists, and albums using embedded Mutagen tags.
  - Displays real-time synchronized lyrics from contiguous `.lrc` files.
  - *Playlist integration in Lune:* Lune does not index raw `.m3u8` files on disk, but supports JSON backup imports. In Lune: *Settings → Import playlists* and select `Canciones/Playlists/lune_playlists_backup.json` delivered by Syncthing.
  - Standard `.m3u8` playlists are generated in parallel for players requiring M3U (VLC, Symfonium, Musicolet, Auxio).
- **Pano Scrobbler:** Scrobbles mobile playback to ListenBrainz in real time or queued offline.

---

## 7. Background Automation (Linux systemd)

The engine runs autonomously on Linux via `systemd` user units:
- **Service Unit:** `~/.config/systemd/user/music-engine.service`
  - Runs `.venv/bin/python main.py run`.
  - Logs output and errors to `logs/systemd.log`.
- **Timer Unit:** `~/.config/systemd/user/music-engine.timer`
  - Triggers the service daily (`OnCalendar=daily`).
  - Persistent activation after reboots (`Persistent=true`, `WantedBy=timers.target`).

---

## 8. CLI Command Reference (`main.py`)

All commands are executed through `main.py` using the Python virtual environment:

```bash
# View engine status, disk usage, and database track counters
.venv/bin/python main.py status

# Run regular periodic engine lifecycle (telemetry, curation, purges, progressive downloads)
.venv/bin/python main.py run

# Fill the Conveyor buffer to maximum capacity (e.g. 750 tracks) in a single run
.venv/bin/python main.py run --fill

# Reassign a track to an official album and move physical files (audio and .lrc)
.venv/bin/python main.py set-album "<Track_or_Search>" "<New_Album_Name>"

# Import a YouTube Music playlist directly into the Permanent library
.venv/bin/python main.py import-playlist <URL_or_ID> [--download]

# Download all queued PENDING tracks without invoking AI curation
.venv/bin/python main.py download-pending

# Audit metadata and auto-repair mismatched tracks (removes cover/karaoke versions)
.venv/bin/python main.py fix-metadata [--use-ai]

# Sync telemetry and heart marks from ListenBrainz only
.venv/bin/python main.py sync-telemetry

# Force regeneration of all .m3u8 playlists and Lune JSON backup
.venv/bin/python main.py update-playlists

# Watch Permanent and Conveyor directories and update playlists in real time
.venv/bin/python main.py watch-folders [--interval 5]

# Scan and enrich lyrics (fetch missing lyrics and upgrade to synchronized .lrc)
.venv/bin/python main.py enrich-lyrics [--limit 50] [--all]

# Classify and embed exact music genres into metadata and SQLite
.venv/bin/python main.py enrich-genres [--limit 50] [--all] [--force-all] [--no-ai]
```

---

## 9. AI Agent & Developer Operating Principles

To maintain codebase cleanliness, user privacy, and architectural consistency over time, every AI coding assistant and human contributor must follow these non-negotiable guidelines:

### 1. English-Only Development Standard
- **Codebase:** All newly authored Python modules, classes, functions, variable names, and constants must be in clear English.
- **Documentation & Comments:** Docstrings, inline code comments, and terminal/log outputs must be written in English.
- **Git Commits:** Every git commit message must be in English following conventional commit patterns (e.g., `feat: ...`, `fix: ...`, `refactor: ...`, `chore: ...`).

### 2. Privacy, Git Hygiene & Zero Data Leakage
- **Never Commit User Data:** The Git repository is publicly shareable and open-source ready. Under no circumstances should real personal databases (`*.sqlite`), backups (`data/backups/`), runtime states (`download_archive.txt`, `taste_profile.json`), authentication tokens (`.env`), cookies (`cookies.txt`), headers (`headers_auth.json`), or audio files (`.opus`, `.m4a`, etc.) be committed or tracked.
- **Proactive `.gitignore` Updates:** When introducing any new feature that produces runtime state, caches, test artifacts, or temporary files, the developer/agent **must verify and update `.gitignore` immediately** before staging files.

### 3. Continuous Documentation Synchronization
- **Always Keep Docs in Sync:** Whenever code, schema tables, configuration options (`config.yaml`), environment variables (`.env`), CLI flags, or lifecycle behaviors are modified, the agent **must update both `CONTEXT.md` and `README.md`**.
- `CONTEXT.md` acts as the deep architectural source of truth, while `README.md` serves as the user-facing installation and operational guide. Neither should ever be left outdated.

### 4. Linux Portability & Non-Blocking Design
- All filesystem access must resolve user homes dynamically via `~` or `os.path.expanduser()` (managed centrally in `src/paths.py`).
- Desktop notifications (`notify-send`) and external CLI utilities must be non-blocking and wrapped in fail-safe try/catch blocks so the engine runs flawlessly across all Linux distributions, window managers, Wayland/X11 compositors, and headless servers.
