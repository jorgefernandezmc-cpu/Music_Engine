# 🎵 Music Engine — The Autonomous Musical Conveyor Belt

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/database-SQLite_WAL-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite WAL">
  <img src="https://img.shields.io/badge/AI-Google_Gemini-4285F4?style=for-the-badge&logo=google&logoColor=white" alt="Google Gemini">
  <img src="https://img.shields.io/badge/downloader-yt--dlp-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="yt-dlp">
  <img src="https://img.shields.io/badge/sync-Syncthing-16A085?style=for-the-badge&logo=syncthing&logoColor=white" alt="Syncthing">
</p>

**Music Engine** is an autonomous, self-hosted, and 100% private music management system. It maintains a local high-fidelity audio library (`.opus` / `.m4a`), autonomously discovers and downloads new music using Artificial Intelligence (Google Gemini) and YouTube Music, prioritizes official studio album versions over loose singles, and syncs bidirectionally with Android devices.

---

## 📑 Table of Contents

- [Core Concepts & Lifecycle](#-core-concepts--lifecycle)
- [System Architecture](#-system-architecture)
- [Prerequisites](#-prerequisites)
- [Step-by-Step Installation](#-step-by-step-installation)
- [Configuration Guide](#-configuration-guide)
  - [1. Storage & Engine Settings (`config/config.yaml`)](#1-storage--engine-settings-configconfigyaml)
  - [2. API Keys & Telemetry (`config/.env`)](#2-api-keys--telemetry-configenv)
  - [3. Seed Taste Profile (`data/taste_profile.json`)](#3-seed-taste-profile-datataste_profilejson)
  - [4. Database Initialization](#4-database-initialization)
  - [5. Optional YouTube Authentication](#5-optional-youtube-authentication)
- [CLI Reference](#-cli-reference)
- [Remote Control Mailbox (`peticiones.txt`)](#-remote-control-mailbox-peticionestxt)
- [Mobile Ecosystem & Sync](#-mobile-ecosystem--sync)
- [Background Automation (Systemd)](#-background-automation-systemd)
- [Codebase Architecture](#-codebase-architecture)
- [Troubleshooting & FAQ](#-troubleshooting--faq)
- [Privacy & Local Storage](#-privacy--local-storage)

---

## 🚀 Core Concepts & Lifecycle

The engine operates around the **"Conveyor Belt" (Cinta Transportadora)** lifecycle model:

```text
       [ AI Curator (Gemini) / YouTube Music ]
                          │
                          ▼
              📦 "Conveyor" Buffer (Cinta/)
                 (Rotating discoveries)
                 │                   │
      Listened Repeatedly?      Unplayed / Skipped?
          (≥15 plays)                │
               or                    ▼
        Marked ❤️ (Love)?       🗑️ Purged (Guillotine)
                 │            (Deleted from disk automatically)
                 ▼
     ⭐ Permanent Library (Permanente/)
      Permanente/<Artist>/<Album>/<Track>.opus
```

1. **Continuous Discovery (`Cinta/`)**: The engine analyzes your listening profile and fills a temporary rotating buffer with new tracks matching your taste.
2. **Promotion to Permanent (`Permanente/`)**: If you listen to a track repeatedly (configurable, default: 15 plays) or mark it with a heart (❤️ Love) on your mobile player, the track is promoted to permanent storage.
3. **Automated Guillotine**: Tracks left unplayed past the grace period (default: 150 days) or frequently skipped are automatically purged from disk to free up space.
4. **Studio Album Hierarchy**: Permanent tracks are strictly organized as:
   ```text
   Permanente/<Primary_Artist>/<Album>/<Primary_Artist> - <Title>.opus
   Permanente/<Primary_Artist>/<Album>/<Primary_Artist> - <Title>.lrc
   ```
5. **Integrated Lyrics**: Automatically extracts synced lyrics (`.lrc`) from multiple sources (LRCLIB, syncedlyrics, YouTube Music, lyrics.ovh) and embeds Vorbis/ID3 lyrics tags.

---

## 📐 System Architecture

```text
 +-----------------------------------------------------------------------+
 |                            MOBILE DEVICE                              |
 |                                                                       |
 |   [ Lune Music Player ] ----> [ Pano Scrobbler ] ----> [ ListenBrainz ]
 |             ^                         |                      |        |
 +-------------|-------------------------|----------------------|--------+
               | (Audio files            |                      |
               |  & .lrc sidecars)       |                      |
               v                         |                      |
      === [ SYNCTHING ] ===              |                      |
               ^                         |                      |
 +-------------|-------------------------|----------------------|--------+
 |             v                         v                      v        |
 |       Music Storage             Heart Feedback          Scrobbles     |
 |       (Canciones/)                    │                      │        |
 |             │                         +-----------┬----------+        |
 |             ▼                                     ▼                   |
 |  +-----------------------------------------------------------------+  |
 |  |                        MUSIC ENGINE (PC)                        |  |
 |  |                                                                 |  |
 |  |  • StoragePaths    : Dynamic directory resolution               |  |
 |  |  • AlbumResolver   : Resolves canonical studio album versions   |  |
 |  |  • TelemetryEngine : Syncs scrobbles and loved tracks           |  |
 |  |  • FileSyncManager : Detects manual moves and cleans ghosts     |  |
 |  |  • CuratorLLM      : Gemini AI + YTM radios recommendation      |  |
 |  |  • Downloader      : yt-dlp batch downloads + metadata tags    |  |
 |  |  • LyricsProvider  : Multi-source fallback synced lyrics (.lrc) |  |
 |  |  • PlaylistGen     : Standard .m3u8 & Lune backup generator     |  |
 |  |                                                                 |  |
 |  |                    SQLite Database (WAL Mode)                   |  |
 |  |                   (data/conveyor_state.sqlite)                  |  |
 |  +-----------------------------------------------------------------+  |
 +-----------------------------------------------------------------------+
```

---

## 🛠️ Prerequisites

Before installing the engine, ensure your system has:

- **Python 3.10+** (tested on 3.10, 3.11, 3.12, 3.13, 3.14).
- **ffmpeg** (required by `yt-dlp` for audio extraction and transcoding):
  ```bash
  # Debian / Ubuntu / Linux Mint (ensure python3-venv is installed)
  sudo apt install python3 python3-venv python3-pip ffmpeg

  # Arch Linux / Manjaro
  sudo pacman -S python ffmpeg

  # Fedora / RHEL
  sudo dnf install python3 python3-pip ffmpeg

  # openSUSE
  sudo zypper install python3 python3-pip ffmpeg

  # Alpine Linux
  apk add python3 py3-pip ffmpeg

  # macOS (Homebrew)
  brew install python ffmpeg
  ```
- **Syncthing** *(Optional, recommended for mobile syncing)*.

---

## 📦 Step-by-Step Installation

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/Music_Engine.git
cd Music_Engine
```

### 2. Set Up a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## ⚙️ Configuration Guide

### 1. Storage & Engine Settings (`config/config.yaml`)

Create your local configuration by copying the template:

```bash
cp config/config.yaml.template config/config.yaml
```

Open `config/config.yaml` and set your base storage directory:

```yaml
storage:
  # Base directory where music will reside (~ expands to your user's home folder):
  base_dir: "~/Music/Songs"
  
  conveyor_dir: "Conveyor"        # Temporary discovery buffer (or "Cinta")
  permanent_dir: "Permanent"      # Permanent library (or "Permanente")
  playlists_dir: "Playlists"      # Generated .m3u8 playlists
  requests_file: "requests.txt"   # Remote commands mailbox file (or "peticiones.txt")
  mass_deletion_failsafe_limit: 50
  max_db_backups: 5

conveyor:
  buffer_size: 750                # Max tracks in rotating buffer
  grace_period_days: 150          # Days without listens before purge
  promotion_play_count: 15        # Scrobbles required to promote to Permanent
  max_skips_before_purge: 5       # Max skips allowed
  max_skip_ratio: 0.7             # Skips-to-plays tolerance ratio
  telemetry_safety_margin_days: 7 # Days without scrobble sync before suspending purges
  curation_batch_per_cycle: 20    # New tracks requested per cycle

llm:
  model: gemini-2.5-flash         # Gemini model (e.g. gemini-2.5-flash, gemini-1.5-flash)
  diversity_weights:
    exploitation: 0.60            # 60% established tastes
    adjacent: 0.25                # 25% adjacent artists/genres
    exploration: 0.15             # 15% brand new discoveries

downloader:
  preferred_codec: "opus"         # Preferred codec: "opus" or "m4a"
  fallback_codec: "m4a"
  batch_size: 50
  cycle_max_downloads: 50
  retry_failed: true
```

### 2. API Keys & Telemetry (`config/.env`)

Create your environment file from the template:

```bash
cp config/.env.template config/.env
```

Edit `config/.env`:

```env
# Required for AI curation: Get a free key at https://aistudio.google.com/
GEMINI_API_KEY=your_gemini_api_key_here

# Optional: ListenBrainz telemetry for scrobble tracking and ❤️ hearts
LISTENBRAINZ_USER=your_listenbrainz_username
LISTENBRAINZ_TOKEN=your_listenbrainz_user_token
```

> [!NOTE]
> Without ListenBrainz credentials, the engine can still curate, download, tag, manage requests, and generate playlists, but play counts and heart shielding will not synchronize from mobile.

### 3. Seed Taste Profile (`data/taste_profile.json`)

To bootstrap the AI curator with your initial preferences before importing playlists, copy the template:

```bash
cp data/taste_profile.json.template data/taste_profile.json
```

Customize your favorite artists and genres in `data/taste_profile.json`:

```json
{
  "total_tracks": 10,
  "top_artists": {
    "ArtistOne": 50,
    "ArtistTwo": 35
  },
  "genre_seeds": ["Indie Rock", "Synthwave", "Hip Hop"]
}
```

*(Note: Once you import playlists using `python main.py import-playlist`, the engine automatically updates this profile).*

### 4. Database Initialization

Initialize the SQLite database schema with WAL mode:

```bash
python3 database/init_db.py
```

This creates `data/conveyor_state.sqlite` with all required tables and indexes.

### 5. Optional YouTube Authentication

By default, downloads and metadata searches work anonymously without authentication. However, if you need to download age-restricted tracks or access private playlists:

- **Browser Cookies (`config/cookies.txt`)**: Export cookies in Netscape format using an extension (such as *Get cookies.txt LOCALLY*) while logged into YouTube.
- **YTMusic Headers (`config/headers_auth.json`)**: Export authentication headers using `ytmusicapi oauth` or copy request headers from the YouTube Music web app.

---

## 💻 CLI Reference

All management tasks are performed via `main.py`:

```bash
# General syntax
python main.py <command> [options]
```

| Command | Arguments | Description |
| :--- | :--- | :--- |
| `status` | — | Shows library statistics, track counts by status, and disk usage. |
| `run` | `[--fill]` | Executes a complete lifecycle cycle (telemetry sync, order processing, purges, AI curation, and downloads). Use `--fill` to replenish the Conveyor buffer completely in one pass. |
| `import-playlist` | `<URL_or_ID> [--download] [--no-album-search]` | Imports a YouTube Music playlist into the Permanent library. Automatically searches official album versions and downloads audio if `--download` is passed. |
| `download-pending` | — | Downloads all queued tracks in `PENDING` status without triggering AI curation. |
| `sync-telemetry` | — | Synchronizes scrobbles and loved tracks from ListenBrainz without running curation or downloading. |
| `update-playlists` | — | Regenerates all `.m3u8` playlists (and Lune JSON backup if enabled in `config.yaml`). |
| `watch-folders` | `[--interval SECONDS]` | Continuously watches the library directories for file movements or additions and updates playlists automatically (default interval: 5s). |
| `set-album` | `"<song>" "<new_album>"` | Reassigns a permanent track to a specific album and moves physical files accordingly on disk. |
| `enrich-lyrics` | `[--limit N] [--all] [--no-upgrade]` | Scans library and downloads missing synchronized lyrics (`.lrc`). |
| `enrich-genres` | `[--limit N] [--all] [--force-all] [--no-ai]` | Classifies music genres via AI and MusicBrainz, injecting tags into files and SQLite. |
| `enrich-metadata` | `[--limit N] [--force-all]` | Enriches track number and release date metadata across audio files and database. |
| `fix-metadata` | `[--use-ai]` | Audits and repairs mismatched or non-album tracks (covers, live recordings, karaoke versions). |

### Quick Execution Script

For convenient execution without typing full commands:

```bash
./scripts/update_now.sh
```

---

## 📱 Remote Control Mailbox (`requests.txt` / `peticiones.txt`)

Inside the root of your synced music directory (`base_dir`), the engine monitors `requests.txt` (or `peticiones.txt`). You can edit this file from your mobile phone to issue commands, request full albums, or download temporary cravings:

```text
# 1. Download full studio albums:
album: Pink Floyd - The Dark Side of the Moon        # Full album to Permanent library
permanent album: Rosalía - Motomami                  # Full album to Permanent library
craving album: Arctic Monkeys - AM                   # Full album to temporary Cravings folder

# 2. Download individual tracks:
Download "Get Lucky" by Daft Punk                    # Single track to Permanent library
permanent: Daft Punk - Get Lucky                     # Single track to Permanent library
craving: Charli xcx - Apple                          # Single track to temporary Cravings folder
antojo: Quevedo - Columbia                           # Temporary craving (purged after retention_days)

# 3. Promote / shield track from Conveyor or Cravings to Permanent:
favorite: Track Name
permanent: Track Name

# 4. Discard / purge track immediately from Conveyor or Cravings:
purge: Track Name
delete: Track Name

# 5. Correct album metadata (reassign song):
album: Track Name -> Official Album Title

# 6. Correct genre metadata:
genre: Track Name -> Synthwave

# 7. Fetch / upgrade synchronized lyrics:
lyrics: Track Name

# 8. Discover new music via thematic radio:
radio: 90s Grunge Rock
```

> [!TIP]
> - **Cravings Folder (`Cravings/` / `Antojos/`)**: Songs and albums queued as cravings are kept temporarily and automatically purged once they exceed the configured retention period (`cravings.retention_days`, default: 30 days).
> - Spanish aliases (`antojo:`, `antojo album:`, `favorita:`, `borrar:`, `genero:`, `letra:`) are fully supported interchangeably.

---

## 📲 Mobile Ecosystem & Sync

To build a seamless, offline-first mobile music experience on Android:

### 1. Syncthing (P2P File Synchronization)
Sync your base music folder (`storage.base_dir`) bidirectionally with your Android device.

Recommended `.stignore` on the root of your music folder:
```text
(?d).venv*
(?d)__pycache__
(?d)*.pyc
(?d)*.lock
(?d)*.tmp
```

### 2. Mobile Music Players & Playlists
- **Universal `.m3u8` Playlists:** Standard `.m3u8` playlists generated by the engine work out of the box with almost all modern Android and desktop players (such as **Auxio**, **Retro Music Player**, **Symfonium**, **Poweramp**, **Strawberry**, **VLC**, and **MPV**).
- **Lune Music Player (Optional):** If you use the [Lune](https://github.com/) Android audio player, you can enable `generate_lune_backup: true` under `playlists:` in `config/config.yaml`. The engine will export `Playlists/lune_playlists_backup.json`, which can be imported in Lune via **Settings → Import playlists**.
- **Synchronized Lyrics:** Contiguous `.lrc` sidecars generated by the engine display real-time lyrics seamlessly across all supported players.

### 3. Pano Scrobbler + ListenBrainz
- Install [Pano Scrobbler](https://github.com/kawaiiDango/pno-scrobbler) on Android and link it to your **ListenBrainz** account.
- Scrobbles and heart marks (❤️) are recorded offline and uploaded whenever an internet connection is available.
- When the PC engine runs `main.py run`, scrobbles are downloaded, play counts incremented, and loved tracks promoted.

---

## ⏰ Background Automation (Systemd)

To automate the engine on Linux so it runs daily in the background:

### 1. Create the systemd service file
`~/.config/systemd/user/music-engine.service`:

```ini
[Unit]
Description=Music Engine Autonomous Runner

[Service]
Type=oneshot
WorkingDirectory=/path/to/Music_Engine
ExecStart=/path/to/Music_Engine/.venv/bin/python main.py run
StandardOutput=append:/path/to/Music_Engine/logs/systemd.log
StandardError=append:/path/to/Music_Engine/logs/systemd.log
```

### 2. Create the systemd timer file
`~/.config/systemd/user/music-engine.timer`:

```ini
[Unit]
Description=Daily run for Music Engine

[Timer]
OnCalendar=*-*-* 04:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

### 3. Enable and activate the timer:
```bash
systemctl --user daemon-reload
systemctl --user enable --now music-engine.timer
```

---

## 🏗️ Codebase Architecture

The project follows a clean modular structure:

| Module | Location | Role |
| :--- | :--- | :--- |
| **CLI & Entry** | [`main.py`](main.py) / [`src/cli.py`](src/cli.py) | CLI argument parser and command orchestrator. |
| **Storage Paths** | [`src/paths.py`](src/paths.py) | Configurable path resolution, folder structures, and directory validation. |
| **Database** | [`src/db.py`](src/db.py) | Centralized SQLite connection pool with WAL mode, index management, and cache tuning. |
| **Sync Manager** | [`src/sync.py`](src/sync.py) | Detects manual folder reorganizations, purges ghost tracks, and guards with mass deletion failsafe. |
| **Order Processor** | [`src/order_processor.py`](src/order_processor.py) | Parses and executes requests from the `peticiones.txt` mailbox. |
| **Lifecycle Engine** | [`src/engine.py`](src/engine.py) | Orchestrates rotation cycles, play-count promotions, heart shielding, and purging. |
| **AI Curator** | [`src/curator_llm.py`](src/curator_llm.py) | Gemini AI recommendation engine and YouTube Music discovery radios. |
| **Album Resolver** | [`src/album_resolver.py`](src/album_resolver.py) | Ensures downloads map to canonical studio albums rather than loose singles. |
| **Downloader** | [`src/downloader.py`](src/downloader.py) | Batch audio extraction with `yt-dlp`, tagging, and format conversion. |
| **Lyrics Provider** | [`src/lyrics_provider.py`](src/lyrics_provider.py) | Multi-source synchronized lyrics provider (LRCLIB, syncedlyrics, YTM). |
| **Genre Resolver** | [`src/genre_resolver.py`](src/genre_resolver.py) | Audio genre classifier using Gemini LLM and MusicBrainz. |
| **Playlist Gen** | [`src/playlist_gen.py`](src/playlist_gen.py) | Fast `.m3u8` playlist generation and Lune JSON backup with in-memory caching. |
| **Telemetry** | [`src/telemetry.py`](src/telemetry.py) | ListenBrainz API scrobble synchronization with fuzzy string matching. |
| **Notifications** | [`src/notifications.py`](src/notifications.py) | Non-blocking Linux desktop notifications via `notify-send`. |

---

## ❓ Troubleshooting & FAQ

### `ERROR: Critical environment variables missing in config/.env`
Ensure you copied `config/.env.template` to `config/.env` and filled in `GEMINI_API_KEY`. The engine requires a valid Gemini API key to operate curation.

### `yt-dlp` fails to extract audio or reports format errors
Make sure **ffmpeg** is installed on your operating system and accessible in your system `PATH`. Test with:
```bash
ffmpeg -version
```

### Database is locked (`sqlite3.OperationalError: database is locked`)
The engine uses SQLite WAL mode with a busy timeout. Ensure no lingering background process or manual SQLite editor has an uncommitted transaction open. Remove `data/engine.lock` if an unexpected system shutdown occurred.

### Tracks being purged unexpectedly
Review your `conveyor` configuration in `config/config.yaml`:
- Increase `grace_period_days` (e.g., 180 or 365) to give you more time to listen to new tracks.
- Check `promotion_play_count` (lower to 5 or 10 if you want songs promoted faster).
- Ensure ListenBrainz scrobbling is active so the engine receives your play counts.

---

## 🔒 Privacy & Local Storage

- **100% Local**: All audio files, playlists, lyrics, and metadata reside directly on your own drives.
- **No Vendor Lock-In**: Standard formats (`.opus`, `.m4a`, `.lrc`, `.m3u8`, SQLite) ensure your collection is accessible by any standard media player.
- **Automated Backups**: The database automatically retains rolling SQLite backups under `data/backups/`.

---

<p align="center">
  <b>Music Engine</b> — Built for self-hosters and passionate music collectors.
</p>
