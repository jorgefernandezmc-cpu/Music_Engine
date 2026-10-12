# 🎵 Music Engine — The Autonomous Musical Conveyor Belt

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/database-SQLite_WAL-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite WAL">
  <img src="https://img.shields.io/badge/AI-Google_Gemini-4285F4?style=for-the-badge&logo=google&logoColor=white" alt="Google Gemini">
  <img src="https://img.shields.io/badge/downloader-yt--dlp-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="yt-dlp">
  <img src="https://img.shields.io/badge/sync-Syncthing-16A085?style=for-the-badge&logo=syncthing&logoColor=white" alt="Syncthing">
  <img src="https://img.shields.io/badge/docs-modular_v2.0-blueviolet?style=for-the-badge" alt="Modular Docs">
</p>

> **Music Engine** is an autonomous, self-hosted, and 100% private music management system. It maintains a local high-fidelity audio library (`.opus` / `.m4a`), autonomously discovers and downloads new music using Artificial Intelligence (Google Gemini) and YouTube Music, strictly prioritizes official studio album versions over loose singles, and synchronizes bidirectionally with Android devices.

---

## 🚀 The "Conveyor Belt" Model

Music Engine replaces static playlists with an **automated musical conveyor belt**:

```text
       [ AI Curator (Gemini) / YouTube Music ]
                          │
                          ▼
              📦 "Conveyor" Buffer (Conveyor/)
                 (Rotating discoveries)
                 │                   │
      Listened Repeatedly?      Unplayed / Skipped?
          (≥15 plays)                │
               or                    ▼
        Marked ❤️ (Love)?       🗑️ Purged (Guillotine)
                 │            (Deleted from disk automatically)
                 ▼
     ⭐ Permanent Library (Permanent/)
      Permanent/<Artist>/<Album>/<Track>.opus
```

1. **Continuous Discovery (`Conveyor/`)**: Analyzes your taste and fills a rotating buffer with new songs.
2. **Promotion to Permanent (`Permanent/`)**: If you listen to a track repeatedly ($\ge 15$ scrobbles) or tap ❤️ (*Love*) on your mobile player, it is permanently saved in its official studio album folder.
3. **Automated Guillotine**: Tracks left unplayed past the grace period (150 days) or frequently skipped are automatically purged from disk to keep your storage lean.
4. **Temporary Cravings (`Cravings/`)**: Queue temporary tracks or summer anthems that automatically expire after 30 days without polluting your permanent library.
5. **Integrated Synced Lyrics (`.lrc`)**: Extracts synchronized karaoke lyrics with millisecond precision from LRCLIB, syncedlyrics, and YouTube Music.

---

## ✨ Key Features at a Glance

- 🧠 **AI-Powered Curation**: Leverages Google Gemini to balance familiarity (60%), adjacent artists (25%), and exploratory discoveries (15%).
- 💿 **Studio Album Integrity**: Enforces strict `Permanent/<Primary_Artist>/<Album>/` organization. Rejects loose singles, bootlegs, and live covers.
- 📱 **Remote Control Mailbox**: Add songs, download full albums, change genres, or purge tracks right from your phone by editing a simple synced text file (`requests.txt` / `peticiones.txt`).
- 📲 **Seamless Mobile Sync**: Bidirectional P2P synchronization with Android via Syncthing. Out-of-the-box compatibility with **Lune**, **Auxio**, **Symfonium**, and **Poweramp**.
- 🎧 **Offline-First Telemetry**: Offline scrobbling via **Pano Scrobbler** + **ListenBrainz** closes the loop: mobile playback counts and favorites drive desktop promotions.
- 💾 **Smart Backups & PC Migration**: Zero-downtime hot SQLite snapshots with SHA-256 deduplication and one-command migration bundles (`.tar.gz`) with automatic path rebasing.
- ⏰ **Unattended Automation**: Fully automated daily execution via non-privileged Linux systemd user timers.

---

## ⚡ Quick Start (3 Steps)

Get up and running in under 2 minutes:

```bash
# 1. Clone repository & install dependencies
git clone https://github.com/your-username/Music_Engine.git && cd Music_Engine
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Setup configuration & secrets
cp config/config.yaml.template config/config.yaml
cp config/.env.template config/.env
# Edit config/.env and add your GEMINI_API_KEY (Free at https://aistudio.google.com/)

# 3. Initialize database & run first check
python database/init_db.py
python main.py status
```

> [!TIP]
> Looking for detailed distribution instructions, troubleshooting, or configuration details? Visit the guides below!

---

## 📚 Documentation Portal

The full documentation is modularly organized in the [`docs/`](docs/) directory:

| Guide | Description | Target Readers |
| :--- | :--- | :--- |
| 📦 **[Installation Guide](docs/installation.md)** | OS packages (`ffmpeg`, `python3-venv`), venv setup for Linux/macOS/WSL2. | *New users, Sysadmins* |
| ⚙️ **[Configuration Guide](docs/configuration.md)** | Deep dive into `config.yaml`, `.env` tokens, taste profile & YouTube auth. | *All users* |
| 💻 **[CLI Reference](docs/cli-reference.md)** | Exhaustive manual for all `main.py` commands, flags (`--fill`, etc.) and examples. | *Power users, Developers* |
| 📱 **[Remote Mailbox Manual](docs/mailbox-commands.md)** | Full syntax for controlling the engine from mobile via `requests.txt` (EN & ES). | *Daily listeners* |
| 📲 **[Mobile Ecosystem & Sync](docs/mobile-and-sync.md)** | Syncthing setup, `.stignore`, Lune/Auxio players, ListenBrainz & Pano Scrobbler. | *Android users* |
| ⏰ **[Background Automation](docs/automation.md)** | Linux `systemd --user` service and timer setup, lingering, and automated logs. | *Sysadmins, Self-hosters* |
| 🎶 **[Metadata, Genres & Lyrics](docs/metadata-and-lyrics.md)** | Synced `.lrc` cascade, Vorbis tags, Gemini genre classification & album repairs. | *Audiophiles* |
| 💾 **[Backups & PC Migration](docs/backup-and-migration.md)** | Hot SQLite snapshots, SHA-256 deduplication, portable bundles & path rebasing. | *All users* |
| ❓ **[Troubleshooting & FAQ](docs/troubleshooting.md)** | Diagnostic commands, common errors (locks, API keys, ffmpeg) and solutions. | *Anyone encountering issues* |
| 🏗️ **[Architecture & Internals](docs/architecture.md)** | Deep technical guide: state machine, SQLite schema, module catalog & guidelines. | *Contributors, Developers* |

👉 **[Explore the Complete Documentation Index (docs/README.md)](docs/README.md)**

---

## 💻 Essential CLI Commands

```bash
# Check current library status and disk usage:
python main.py status

# Run regular engine cycle (telemetry, curation, purges, downloads):
python main.py run

# Completely fill the Conveyor discovery buffer in a single pass:
python main.py run --fill

# Import a YouTube Music playlist into the Permanent library:
python main.py import-playlist "https://music.youtube.com/playlist?list=..." --download

# Enrich library with synchronized lyrics (.lrc):
python main.py enrich-lyrics --all

# Create a hot backup snapshot of your library state:
python main.py backup --tag "my_backup"
```

*For complete command flags and usage recipes, see the **[CLI Reference](docs/cli-reference.md)**.*

---

## 📱 Mobile Control at a Glance (`requests.txt`)

Control your music library from your phone by typing natural commands in `requests.txt`:

```text
# Download complete studio albums:
album: Pink Floyd - The Dark Side of the Moon
craving album: Arctic Monkeys - AM

# Download single tracks:
permanent: Daft Punk - Get Lucky
craving: Charli xcx - Apple

# Promote or discard tracks:
favorite: Midnight City
purge: Unwanted Track

# Reassign album or correct genres:
album: Track Title -> Correct Studio Album
genre: Track Title -> Synthwave
```

*Spanish keywords (`antojo:`, `disco:`, `favorita:`, `borrar:`, `genero:`) are fully supported interchangeably. See the **[Remote Mailbox Guide](docs/mailbox-commands.md)**.*

---

## 📐 System Architecture

```text
 +-----------------------------------------------------------------------+
 |                            MOBILE DEVICE                              |
 |   [ Lune Music Player ] ----> [ Pano Scrobbler ] ----> [ ListenBrainz ]
 |             ^                         |                      |        |
 +-------------|-------------------------|----------------------|--------+
               | (Audio & .lrc)          |                      |
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
 |  |  • StoragePaths    : Dynamic directory resolution               |  |
 |  |  • AlbumResolver   : Resolves canonical studio album versions   |  |
 |  |  • TelemetryEngine : Syncs scrobbles and loved tracks           |  |
 |  |  • CuratorLLM      : Gemini AI + YTM radios recommendation      |  |
 |  |  • Downloader      : yt-dlp batch downloads + metadata tags    |  |
 |  |  • LyricsProvider  : Multi-source fallback synced lyrics (.lrc) |  |
 |  |  • PlaylistGen     : Standard .m3u8 & Lune backup generator     |  |
 |  |  • BackupManager   : Hot WAL snapshots & deduplication          |  |
 |  |                                                                 |  |
 |  |                    SQLite Database (WAL Mode)                   |  |
 |  |                   (data/conveyor_state.sqlite)                  |  |
 |  +-----------------------------------------------------------------+  |
 +-----------------------------------------------------------------------+
```

---

## 🔒 Privacy & Local Storage

- **100% Local & Self-Hosted**: All audio tracks, playlists, synchronized lyrics, and metadata reside exclusively on your personal drives.
- **No Vendor Lock-In**: Standard, open formats (`.opus`, `.m4a`, `.lrc`, UTF-8 `.m3u8`, SQLite) guarantee seamless playback in any media player.
- **Zero Data Leakage**: Your listening database, API keys, cookies, and music files are strictly git-ignored and never shared externally.

---

<p align="center">
  <b>Music Engine</b> — Built for self-hosters and passionate music collectors.<br>
  <a href="docs/README.md"><b>📖 Browse the Documentation Portal</b></a>
</p>
