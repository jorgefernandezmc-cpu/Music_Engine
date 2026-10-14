# 🏗️ System Architecture & Codebase Internals

<p align="right">
  <b>Language / Idioma:</b>
  <b>English</b> | <a href="../es/architecture.md">Español</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/architecture-modular_python-blue?style=for-the-badge&logo=python&logoColor=white" alt="Modular Python">
  <img src="https://img.shields.io/badge/database-SQLite_WAL-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite WAL">
  <img src="https://img.shields.io/badge/role-developer_reference-green?style=for-the-badge" alt="Developer Reference">
</p>

This technical reference provides an in-depth architectural breakdown of **Music Engine** for developers, sysadmins, and AI coding agents extending or maintaining the codebase.

---

## 📑 Table of Contents

- [System Topology & High-Level Flow](#-system-topology--high-level-flow)
- [The Conveyor Belt State Machine](#-the-conveyor-belt-state-machine)
- [SQLite Database Schema & Indices](#-sqlite-database-schema--indices)
- [Filesystem Storage Hierarchy](#-filesystem-storage-hierarchy)
- [Module Catalog & Component Responsibilities](#-module-catalog--component-responsibilities)
- [Concurrency & Locking Model](#-concurrency--locking-model)
- [Developer & Contributor Directives](#-developer--contributor-directives)

---

## 📐 System Topology & High-Level Flow

```text
 ┌───────────────────────────────────────────────────────────────────────┐
 │                            MOBILE CLIENT                              │
 │                                                                       │
 │   [ Lune Music Player ] ─────▶ [ Pano Scrobbler ] ─────▶ [ListenBrainz│
 │             ▲                          |                   Cloud API] │
 └─────────────┼──────────────────────────┼───────────────────────┼──────┘
               │                          │                       │
               │ Audio files              │ Heart feedback        │ Scrobbles
               │ & .lrc sidecars          │ (Loved tracks)        │ (Play events)
               ▼                          │                       │
      === [ SYNCTHING ] ===               │                       │
               ▲                          │                       │
 ┌─────────────┼──────────────────────────┼───────────────────────┼──────┐
 │             ▼                          ▼                       ▼      │
 │       Canciones Root             Heart Updates           API Scrobbles │
 │       (storage.base_dir)               │                       │      │
 │             │                          └───────────┬───────────┘      │
 │             ▼                                      ▼                  │
 │  ┌─────────────────────────────────────────────────────────────────┐  │
 │  │                        MUSIC ENGINE (PC)                        │  │
 │  │                                                                 │  │
 │  │  • StoragePaths    : Path translation & alias abstraction       │  │
 │  │  • AlbumResolver   : Studio album heuristic matching (+100)    │  │
 │  │  • TelemetryEngine : ListenBrainz sync & fuzzy title matching   │  │
 │  │  • FileSyncManager : Manual move detection & ghost purging      │  │
 │  │  • OrderProcessor  : requests.txt command mailbox parser        │  │
 │  │  • CuratorLLM      : Gemini AI curation + YTM radio generator   │  │
 │  │  • Downloader      : yt-dlp batch extractor + Vorbis tagging    │  │
 │  │  • LyricsProvider  : Multi-source fallback synced lyrics (.lrc) │  │
 │  │  • PlaylistGen     : UTF-8 M3U8 & Lune JSON backup compiler     │  │
 │  │  • BackupManager   : Hot WAL snapshots & portable tar.gz bundles│  │
 │  │                                                                 │  │
 │  │                    SQLite Database (WAL Mode)                   │  │
 │  │                   (data/conveyor_state.sqlite)                  │  │
 │  └─────────────────────────────────────────────────────────────────┘  │
 │                                LINUX PC                                │
 └───────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 The Conveyor Belt State Machine

Every track known to the engine transitions through a deterministic state machine:

```text
                     ┌───────────────┐
                     │  AI Curator / │
                     │  User Request │
                     └───────┬───────┘
                             │
                             ▼
                     ┌───────────────┐
            ┌───────▶│    PENDING    │◀────────┐
            │        └───────┬───────┘         │
            │ Download       │ Download        │ Download
            │ Error          │ Success         │ (Antojo)
            │                ▼                 │
     ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
     │    FAILED    │ │    CINTA     │ │    ANTOJO    │
     └──────────────┘ │  (Conveyor)  │ │  (Cravings)  │
                      └──────┬───────┘ └──────┬───────┘
                             │                │
            ┌────────────────┼────────────────┤
            │ ≥15 plays OR   │                │ Retention
            │ ❤️ Loved Track  │ Unplayed       │ Expiry
            │                │ (150 days)     │ (30 days)
            ▼                ▼                ▼
     ┌──────────────┐ ┌───────────────────────────────┐
     │  PERMANENT   │ │            PURGED             │
     │  (Protected) │ │   (Deleted, Never Re-added)   │
     └──────────────┘ └───────────────────────────────┘
```

### Track Status Definitions

| Status | Lifetime | Location on Disk | Description |
| :--- | :--- | :--- | :--- |
| `PENDING` | Transient | None (queued) | Video ID cataloged; awaiting download via `Downloader`. |
| `CINTA` | Ephemeral | `Conveyor/<Artist> - <Title>.opus` | Active discovery track rotating on the conveyor belt. |
| `PERMANENT` | Indefinite | `Permanent/<Artist>/<Album>/<Track>.opus` | Official collection track. Untouchable by automated purges. |
| `ANTOJO` | 30 Days | `Cravings/<Artist>/<Album>/<Track>.opus` | Temporary craving track; purged after `retention_days`. |
| `PURGED` | Permanent | None (file deleted from disk) | Discarded track. Retained in database to avoid re-curating. |
| `FAILED` | Transient | None | Download error; automatically reset to `PENDING` on next run. |

---

## 🗄️ SQLite Database Schema & Indices

Located at `data/conveyor_state.sqlite`. Defined in [`database/schema.sql`](../../database/schema.sql).

### `tracks` Table
```sql
CREATE TABLE tracks (
    id TEXT PRIMARY KEY,                 -- YouTube Video ID (e.g. 'dQw4w9WgXcQ')
    title TEXT NOT NULL,                 -- Normalized track title
    artist TEXT NOT NULL,                -- Full artist string (with collaborators)
    album TEXT,                          -- Canonical studio album title
    duration_seconds INTEGER,            -- Exact track length
    status TEXT NOT NULL,                -- PENDING, CINTA, PERMANENT, ANTOJO, PURGED, FAILED
    is_permanent BOOLEAN DEFAULT 0,      -- 1 if permanent, 0 otherwise
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_played_at DATETIME,             -- UTC timestamp of most recent scrobble
    play_count INTEGER DEFAULT 0,        -- Cumulative scrobble counter
    skip_count INTEGER DEFAULT 0,        -- Cumulative skipped listens
    file_path TEXT,                      -- Absolute path to physical audio file
    genre TEXT,                          -- Assigned musical genre
    track_number INTEGER,                -- Official album track index
    release_date TEXT                    -- Official release date (YYYY-MM-DD or YYYY)
);
```

### `listen_events` Table
```sql
CREATE TABLE listen_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id TEXT NOT NULL,
    listened_at DATETIME NOT NULL,
    source TEXT,                         -- 'listenbrainz'
    FOREIGN KEY(track_id) REFERENCES tracks(id)
);
```

### `artist_genres` Table
```sql
CREATE TABLE artist_genres (
    artist TEXT PRIMARY KEY,
    genre TEXT NOT NULL,
    source TEXT NOT NULL,                -- 'musicbrainz', 'gemini', 'user'
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### High-Performance Indices
```sql
CREATE INDEX idx_tracks_status ON tracks(status);
CREATE INDEX idx_tracks_status_perm ON tracks(status, is_permanent);
CREATE INDEX idx_tracks_file_path ON tracks(file_path);
CREATE INDEX idx_tracks_artist_title ON tracks(artist, title);
CREATE INDEX idx_tracks_play_count ON tracks(play_count);
CREATE INDEX idx_listen_events_track_id ON listen_events(track_id);
CREATE INDEX idx_listen_events_listened_at ON listen_events(listened_at);
```

---

## 📁 Filesystem Storage Hierarchy

Configured via `storage.base_dir` in `config/config.yaml`:

```text
~/Music/Songs/
├── requests.txt                     # Remote mailbox for commands & orders
│
├── Conveyor/                        # Ephemeral discovery buffer (flat directory)
│   ├── Artist A - Song One.opus
│   ├── Artist A - Song One.lrc
│   └── Artist B - Song Two.opus
│
├── Permanent/                       # Permanent library (strict 2-level hierarchy)
│   ├── Daft Punk/
│   │   ├── Discovery/
│   │   │   ├── Daft Punk - One More Time.opus
│   │   │   ├── Daft Punk - One More Time.lrc
│   │   │   └── Daft Punk - Aerodynamic.opus
│   │   └── Random Access Memories/
│   │       ├── Daft Punk - Get Lucky.opus
│   │       └── Daft Punk - Get Lucky.lrc
│   └── Pink Floyd/
│       └── The Dark Side of the Moon/
│           ├── Pink Floyd - Time.opus
│           └── Pink Floyd - Time.lrc
│
├── Cravings/                        # Temporary cravings collection
│   └── Charli xcx/
│       └── Brat/
│           ├── Charli xcx - Apple.opus
│           └── Charli xcx - Apple.lrc
│
└── Playlists/                       # Auto-generated UTF-8 playlists & Lune backups
    ├── Permanent.m3u8
    ├── Conveyor.m3u8
    ├── Priority_Discovery.m3u8
    ├── Live_Rotation.m3u8
    ├── Cravings.m3u8
    ├── lune_playlists_backup.json   # Native Lune Android backup
    ├── Artistas/                    # Per-artist playlists
    │   ├── Daft Punk.m3u8
    │   └── Pink Floyd.m3u8
    └── Listas Propias/              # User playlists exported from Lune
        └── Workout Energy.m3u8
```

> [!IMPORTANT]
> **Strict Hierarchy Rule:** Inside `Permanent/`, audio files are strictly filed as `Permanent/<Primary_Artist>/<Album>/`. Intermediate folders like `Favorites/`, `Singles/` or `Discoveries/` are disallowed to preserve folder cleanliness and scrobbler predictability.

---

## 🧩 Module Catalog & Component Responsibilities

All core Python modules reside in [`src/`](../../src/):

| Module | Primary Class / Functions | Key Responsibilities |
| :--- | :--- | :--- |
| [`src/paths.py`](../../src/paths.py) | `StoragePaths` | Dynamic resolution of home paths (`~`), directory sanitization, English/Spanish folder aliases. |
| [`src/db.py`](../../src/db.py) | `get_db_connection` | Thread-safe connection pool with WAL mode (`PRAGMA journal_mode=WAL`), busy timeout (30s), cache sizing. |
| [`src/album_resolver.py`](../../src/album_resolver.py) | `resolve_album_track`, `get_primary_artist` | Semantic studio album resolution, heuristic scoring (+100 for albums), antagonistic keyword exclusion. |
| [`src/downloader.py`](../../src/downloader.py) | `Downloader` | Batch audio extraction via `yt-dlp`, Vorbis/MP4 tagging, artwork embedding, rate-limit sleep intervals. |
| [`src/engine.py`](../../src/engine.py) | `MusicEngine` | Central lifecycle orchestrator: runs radar, backups, sync, telemetry, purges, promotions, and downloads. |
| [`src/curator_llm.py`](../../src/curator_llm.py) | `CuratorLLM` | Gemini GenAI API prompts, listening profile analysis, YouTube Music radio recommendations. |
| [`src/telemetry.py`](../../src/telemetry.py) | `TelemetryEngine` | ListenBrainz API integration, fuzzy string matching (`thefuzz`) between remote scrobbles and local tracks. |
| [`src/order_processor.py`](../../src/order_processor.py) | `OrderProcessor` | Parsing natural language and regex commands from `requests.txt`, album moves, and purge requests. |
| [`src/lyrics_provider.py`](../../src/lyrics_provider.py) | `LyricsProvider` | Synchronized `.lrc` lyrics cascade: LRCLIB $\rightarrow$ syncedlyrics $\rightarrow$ YouTube Music $\rightarrow$ lyrics.ovh. |
| [`src/genre_resolver.py`](../../src/genre_resolver.py) | `resolve_genre`, `enrich_library_genres` | Granular genre classification using local SQLite cache, MusicBrainz API, and Gemini AI. |
| [`src/enrich_track_meta.py`](../../src/enrich_track_meta.py) | `enrich_library_metadata` | Ingests canonical track numbers and release dates into audio tags and database. |
| [`src/playlist_gen.py`](../../src/playlist_gen.py) | `PlaylistGenerator` | UTF-8 `.m3u8` playlist compilation, Lune JSON backup generation, and real-time directory watchdogs. |
| [`src/backup_manager.py`](../../src/backup_manager.py) | `BackupManager` | Hot SQLite snapshots, SHA-256 deduplication, single-file `.tar.gz` bundle exports, cross-PC path rebasing. |
| [`src/sync.py`](../../src/sync.py) | `FileSyncManager` | Detects manual file reorganizations, cleans orphaned `.lrc` sidecars, enforces mass-deletion failsafes. |
| [`src/notifications.py`](../../src/notifications.py) | `send_notification` | Non-blocking Linux desktop notifications via `notify-send` with graceful headless fallbacks. |
| [`src/cli.py`](../../src/cli.py) | `main` | Argument parsing and subcommands routing for `main.py`. |

---

## 🔒 Concurrency & Locking Model

Music Engine employs a multi-tiered safety model to prevent race conditions:

1. **Process-Level Lock:** On startup, `MusicEngine` acquires an exclusive filesystem lock on `data/engine.lock` using the Python `filelock` library. If a scheduled cron job or systemd timer fires while a manual run is in progress, the second process exits gracefully.
2. **SQLite WAL Concurrency:** SQLite operates in WAL (Write-Ahead Logging) mode with `PRAGMA synchronous=NORMAL` and a 30,000 ms busy timeout, enabling concurrent readers while background threads write.
3. **Mass Deletion Failsafe:** Implemented in `FileSyncManager`. If more than 50 files are deleted simultaneously outside the engine's supervision, purges are temporarily paused to protect against accidental disk disconnection.

---

## 🤖 Developer & Contributor Directives

All human contributors and AI coding assistants must adhere to the directives defined in [`CONTEXT.md`](../../CONTEXT.md):

1. **English Only:** All code, variables, functions, docstrings, comments, log lines, and git commits must be written in clear English.
2. **Data Privacy & Git Hygiene:** Never commit personal audio files, user databases (`*.sqlite`), backups (`data/backups/`), auth tokens (`.env`), or browser cookies (`cookies.txt`). Always update `.gitignore` when introducing new runtime state.
3. **Continuous Documentation Synchronization:** Any change to the database schema, CLI flags, configuration parameters, or engine architecture must be updated simultaneously in both `README.md`, `CONTEXT.md`, and the relevant files in `docs/`.

---

<p align="center">
  <a href="troubleshooting.md"><b>⬅ Troubleshooting & FAQ</b></a> • <a href="README.md"><b>Return to Documentation Portal ➡</b></a>
</p>
