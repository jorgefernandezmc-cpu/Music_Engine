# ⚙️ Configuration & Setup Guide

<p align="right">
  <b>Language / Idioma:</b>
  <b>🇬🇧 English</b> | <a href="../es/configuration.md">🇪🇸 Español</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/guide-configuration-orange?style=for-the-badge&logo=gear&logoColor=white" alt="Configuration Guide">
  <img src="https://img.shields.io/badge/format-YAML%20&%20ENV-blue?style=for-the-badge" alt="YAML and ENV">
</p>

This guide explains how to configure every aspect of **Music Engine**: filesystem paths, rotation buffers, AI curation parameters, environment variables, database initialization, and optional YouTube authentication.

---

## 📑 Table of Contents

- [Overview of Configuration Files](#-overview-of-configuration-files)
- [1. Storage & Engine Settings (`config/config.yaml`)](#1-storage--engine-settings-configconfigyaml)
  - [Storage Paths](#storage-paths)
  - [Conveyor Lifecycle & Rotation Rules](#conveyor-lifecycle--rotation-rules)
  - [AI Curator (Google Gemini)](#ai-curator-google-gemini)
  - [Downloader & Codec Settings](#downloader--codec-settings)
  - [Telemetry (ListenBrainz)](#telemetry-listenbrainz)
  - [Playlists & Lune Player Integration](#playlists--lune-player-integration)
  - [Smart Backups & Retention](#smart-backups--retention)
- [2. Environment Secrets (`config/.env`)](#2-environment-secrets-configenv)
  - [Obtaining a Gemini API Key](#obtaining-a-gemini-api-key-free)
  - [Setting Up ListenBrainz Telemetry](#setting-up-listenbrainz-telemetry-optional-recommended)
- [3. Taste Profile Seed (`data/taste_profile.json`)](#3-taste-profile-seed-datataste_profilejson)
- [4. Database Initialization (`init_db.py`)](#4-database-initialization-init_dbpy)
- [5. Optional YouTube Authentication](#5-optional-youtube-authentication)
- [Configuration Verification](#-configuration-verification)

---

## 📂 Overview of Configuration Files

```text
config/
├── config.yaml.template    # Blueprint template with documented default values
├── config.yaml             # Your active configuration (git-ignored)
├── .env.template           # Template for API keys and secret tokens
├── .env                    # Your secret credentials (git-ignored)
├── headers_auth.json       # Optional YTMusic authentication headers
└── cookies.txt             # Optional browser cookies for age-restricted songs
```

---

## 1. Storage & Engine Settings (`config/config.yaml`)

Create your active configuration file by copying the template:

```bash
cp config/config.yaml.template config/config.yaml
```

Edit `config/config.yaml` in your preferred text editor.

### Storage Paths

```yaml
storage:
  # Base directory where all your music, playlists, and requests reside.
  # The ~ character automatically expands to your home directory:
  base_dir: "~/Music/Songs"

  # Subfolders relative to base_dir:
  conveyor_dir: "Conveyor"        # Temporary discovery buffer (or "Cinta")
  permanent_dir: "Permanent"      # Permanent collection (or "Permanente")
  cravings_dir: "Cravings"        # Temporary cravings collection (or "Antojos")
  playlists_dir: "Playlists"      # Directory where .m3u8 playlists are generated
  
  # Mailbox file for remote commands (synced with mobile via Syncthing):
  requests_file: "requests.txt"   # Or "peticiones.txt"
  
  # Safety threshold to prevent accidental mass deletions:
  mass_deletion_failsafe_limit: 50
  
  # Maximum rolling database backups to keep:
  max_db_backups: 5
```

> [!NOTE]
> Spanish aliases (`cinta_dir`, `permanente_dir`, `antojos_dir`, `peticiones_file`) are fully supported backwards-compatibly.

---

### Conveyor Lifecycle & Rotation Rules

Controls how songs circulate through the discovery buffer before being promoted or purged:

```yaml
conveyor:
  # Maximum target capacity of songs rotating on the Conveyor:
  buffer_size: 750

  # Days a track can remain unplayed before the Guillotine purges it:
  grace_period_days: 150

  # Total scrobbles required to automatically promote a track to Permanent:
  promotion_play_count: 15

  # Maximum skips allowed before a track is discarded:
  max_skips_before_purge: 5

  # Ratio of skips to completed plays tolerated (0.7 = 70% skip rate):
  max_skip_ratio: 0.7

  # Safety margin: If no telemetry sync occurs for N days, purges are suspended:
  telemetry_safety_margin_days: 7

  # Number of new recommendations requested per regular background cycle:
  curation_batch_per_cycle: 20
```

---

### AI Curator (Google Gemini)

```yaml
llm:
  # Gemini model to use for curation and music analysis:
  # Options: gemini-2.5-flash, gemini-1.5-flash
  model: gemini-2.5-flash

  # Diversity weights (must sum to 1.0):
  diversity_weights:
    exploitation: 0.60    # 60% direct affinity with established favorites
    adjacent: 0.25        # 25% adjacent artists or similar genres
    exploration: 0.15     # 15% brand-new genres and styles
```

---

### Downloader & Codec Settings

```yaml
downloader:
  audio_format: "bestaudio/best"
  preferred_codec: "opus"         # "opus" (recommended for quality/size) or "m4a"
  fallback_codec: "m4a"
  sleep_interval_min: 3           # Random delay in seconds between downloads
  sleep_interval_max: 8           # Prevents rate limiting
  batch_size: 50
  cycle_max_downloads: 50         # Max songs downloaded per run cycle
  retry_failed: true              # Automatically retry previous download errors
```

---

### Telemetry (ListenBrainz)

```yaml
telemetry:
  listenbrainz_url: "https://api.listenbrainz.org/1"
  fuzzy_threshold: 80                 # Minimum match percentage for scrobbles
  loved_fuzzy_artist_threshold: 80
  loved_fuzzy_title_threshold: 85
  lookback_days: 30                   # Days of listening history to scan
```

---

### Playlists & Lune Player Integration

```yaml
playlists:
  auto_update_on_change: true
  min_artist_tracks: 10          # Min tracks by an artist to generate an artist playlist
  
  # Lune Android player native integration:
  generate_lune_backup: true     # Generates lune_playlists_backup.json for Android import
  lune_include_artists: false    # If true, includes artist playlists inside Lune backup
  lune_backup_file: "lune_playlists_backup.json"
  user_playlists_dir: "Listas Propias" # Subfolder for user-created playlists exported from Lune
  
  system_names:
    permanent: "Permanent"
    conveyor: "Conveyor"
    priority_discovery: "Priority_Discovery"
    live_rotation: "Live_Rotation"
    cravings: "Cravings"
```

---

### Smart Backups & Retention

```yaml
backup:
  auto_backup: true              # Create snapshot on each engine run cycle
  dir: "data/backups"            # Target destination folder (~ expands to home)
  max_backups: 10                # Maximum snapshots to keep before automatic rotation
  format: "bundle"               # "bundle" (.tar.gz archive) or "db_only" (.sqlite.gz)
  dedup_by_hash: true            # Skip snapshot if database hash is unchanged
  include_aux_files: true        # Include taste profile, archives, and state
```

---

## 2. Environment Secrets (`config/.env`)

Copy the environment secrets template:

```bash
cp config/.env.template config/.env
```

Edit `config/.env`:

```env
# Required for AI curation:
GEMINI_API_KEY=AIzaSyYourGeneratedGeminiKeyHere

# Optional for scrobble sync and ❤️ heart feedback:
LISTENBRAINZ_USER=your_username
LISTENBRAINZ_TOKEN=your_listenbrainz_user_token
```

### Obtaining a Gemini API Key (Free)
1. Navigate to [Google AI Studio](https://aistudio.google.com/).
2. Sign in with your Google account.
3. Click on **Get API key** and generate a new key.
4. Paste it as `GEMINI_API_KEY` in `config/.env`.

### Setting Up ListenBrainz Telemetry (Optional, Recommended)
1. Create a free account at [ListenBrainz.org](https://listenbrainz.org/).
2. Go to **Settings** → **API Token**.
3. Copy your username into `LISTENBRAINZ_USER` and the token into `LISTENBRAINZ_TOKEN`.

> [!TIP]
> Without ListenBrainz, Music Engine will still download, tag, curate, and organize playlists. However, automatic promotion based on play count and ❤️ heart shielding from mobile will not take place.

---

## 3. Taste Profile Seed (`data/taste_profile.json`)

To bootstrap the AI curator with your initial preferences before you import any playlists, copy the template:

```bash
cp data/taste_profile.json.template data/taste_profile.json
```

Edit `data/taste_profile.json` with a few favorite artists and genres:

```json
{
  "total_tracks": 10,
  "top_artists": {
    "Daft Punk": 50,
    "Pink Floyd": 40,
    "Arctic Monkeys": 30
  },
  "genre_seeds": [
    "Electronic",
    "Psychedelic Rock",
    "Indie Rock"
  ]
}
```

> [!NOTE]
> Whenever you import YouTube Music playlists via `python main.py import-playlist`, the engine automatically updates this file with your real listening distribution.

---

## 4. Database Initialization (`init_db.py`)

Run the database initialization script to create the SQLite database in WAL (Write-Ahead Logging) mode:

```bash
python database/init_db.py
```

*Output:*
```text
Database data/conveyor_state.sqlite initialized successfully in WAL mode.
```

This creates `data/conveyor_state.sqlite` with all necessary tables (`tracks`, `listen_events`, `system_metadata`, `orphan_scrobbles`, `artist_genres`) and high-performance search indices.

---

## 5. Optional YouTube Authentication

By default, downloads and metadata work anonymously. However, if you plan to import private playlists or download age-restricted tracks:

### Browser Cookies (`config/cookies.txt`)
1. In your browser (Firefox, Chrome, Brave), install an extension like *Get cookies.txt LOCALLY*.
2. Log into YouTube.
3. Export your cookies in Netscape format.
4. Save the exported file as `config/cookies.txt`.

### YTMusic Headers (`config/headers_auth.json`)
If you want to authenticate your personal YouTube Music account:
1. Run `ytmusicapi oauth` in your terminal and follow the instructions, OR
2. Copy request headers from the YouTube Music web app (Network tab in DevTools) and save to `config/headers_auth.json`.

---

## 🔍 Configuration Verification

Test that everything is properly configured by checking the status:

```bash
python main.py status
```

*Expected output:*
```text
=============================================
 CONVEYOR BELT STATUS
=============================================
Base directory:     /home/username/Music/Songs
Tracks in CONVEYOR: 0
PERMANENT tracks:   0
CRAVINGS tracks:    0
PENDING tracks:     0
PURGED tracks:      0
---------------------------------------------
Disk space used:    0.00 MB
Last scrobble:      None
Last LB sync:       Never
=============================================
```

---

<p align="center">
  <a href="installation.md"><b>⬅ Installation Guide</b></a> • <a href="cli-reference.md"><b>Next: CLI Reference ➡</b></a>
</p>
