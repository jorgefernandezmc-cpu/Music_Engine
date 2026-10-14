# 📚 Music Engine Documentation Portal

<p align="right">
  <b>Language / Idioma:</b>
  <b>🇬🇧 English</b> | <a href="../es/README.md">🇪🇸 Español</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/docs-v2.0-blue?style=for-the-badge" alt="Documentation Version">
  <img src="https://img.shields.io/badge/coverage-complete-brightgreen?style=for-the-badge" alt="Coverage Complete">
  <img src="https://img.shields.io/badge/audience-all_users-orange?style=for-the-badge" alt="Audience All Users">
</p>

Welcome to the comprehensive documentation portal for **Music Engine** — the autonomous, self-hosted, and 100% private music management ecosystem.

Whether you are setting up the system for the very first time, looking up CLI commands, integrating Android playback and scrobbling, or contributing code to the core engine, you will find targeted, detailed guides below.

---

## 🗺️ Documentation Directory

```text
docs/en/
├── README.md               # 📍 You are here: Documentation index and navigational roadmap
├── installation.md         # 📦 Prerequisites, OS packages (Linux/macOS/WSL2), venv & dependencies
├── configuration.md        # ⚙️ config.yaml reference, .env secrets, taste profile & database init
├── cli-reference.md        # 💻 Exhaustive CLI commands, arguments, flags and real-world examples
├── mailbox-commands.md     # 📱 Remote control requests.txt / peticiones.txt syntax (EN & ES)
├── mobile-and-sync.md      # 📲 Syncthing P2P sync, Lune & Android players, ListenBrainz telemetry
├── automation.md           # ⏰ Background automation via systemd user services, timers & logging
├── metadata-and-lyrics.md  # 🎶 Synced .lrc lyrics cascade, AI genre tagging & studio album repairs
├── backup-and-migration.md # 💾 Hot SQLite snapshots, SHA-256 deduplication & PC migration bundles
├── troubleshooting.md      # ❓ Comprehensive FAQ, common errors, diagnostics & recovery steps
└── architecture.md         # 🏗️ Deep technical internals, SQLite data model & module catalog
```

---

## 🎯 Documentation by User Role

Find the path that matches your current goal:

| User Profile | Recommended Reading Path |
| :--- | :--- |
| **🚀 First-Time User** | 1. [Installation Guide](installation.md)<br>2. [Configuration Guide](configuration.md)<br>3. [Mobile Ecosystem & Sync](mobile-and-sync.md) |
| **🎧 Daily Music Listener** | 1. [Remote Mailbox Commands](mailbox-commands.md)<br>2. [Mobile Ecosystem & Sync](mobile-and-sync.md)<br>3. [CLI Reference](cli-reference.md) |
| **🛠️ Self-Hoster & Sysadmin** | 1. [Background Automation (Systemd)](automation.md)<br>2. [Backups & PC Migration](backup-and-migration.md)<br>3. [Troubleshooting & FAQ](troubleshooting.md) |
| **🎵 Audiophile & Tag Curator** | 1. [Metadata, Genres & Lyrics](metadata-and-lyrics.md)<br>2. [Configuration Guide](configuration.md) (codecs, heuristics) |
| **💻 Developer & Contributor** | 1. [System Architecture & Internals](architecture.md)<br>2. [CLI Reference](cli-reference.md)<br>3. [Root CONTEXT.md](../../CONTEXT.md) |

---

## 📑 Guides Overview

### 1. 📦 [Installation Guide](installation.md)
Step-by-step setup instructions for Debian, Ubuntu, Arch, Fedora, openSUSE, Alpine, macOS, and Windows WSL2. Covers system packages (`python3-venv`, `ffmpeg`), repository cloning, virtual environment configuration, and verification commands.

### 2. ⚙️ [Configuration Guide](configuration.md)
Complete line-by-line explanation of every setting in `config/config.yaml`: storage paths, Conveyor rotation limits, Gemini AI curation weights, downloader parameters, and backup policies. Details API credentials in `config/.env`, initial taste profile bootstrapping in `data/taste_profile.json`, database initialization, and optional YouTube cookies/headers.

### 3. 💻 [CLI Reference](cli-reference.md)
Full manual for `main.py` containing syntax, every command, all available arguments, flags (`--fill`, `--download`, `--force-all`, `--use-ai`, `--no-rebase`, etc.), and practical recipes for everyday maintenance.

### 4. 📱 [Remote Mailbox Commands (`requests.txt`)](mailbox-commands.md)
Learn how to control the engine from your phone by editing a simple synced text file. Covers English and Spanish syntax for single tracks, complete studio albums, temporary cravings, favorite promotions, genre reclassification, lyrics refresh, and purges.

### 5. 📲 [Mobile Ecosystem & Sync](mobile-and-sync.md)
How to create a seamless offline music experience: setting up bidirectional Syncthing with optimized `.stignore` rules, configuring offline-first players (**Lune**, **Auxio**, **Symfonium**, **VLC**), extracting custom user playlists, and tracking plays and hearts with **Pano Scrobbler** and **ListenBrainz**.

### 6. ⏰ [Background Automation (Systemd)](automation.md)
Automate Music Engine on Linux using non-privileged `systemd --user` units. Includes ready-to-use `.service` and `.timer` configurations, persistent wakeups, logging, and cronjob alternatives.

### 7. 🎶 [Metadata, Genres & Lyrics](metadata-and-lyrics.md)
Deep dive into the media enrichment pipeline: multi-source synced lyrics cascade (LRCLIB, syncedlyrics, YouTube Music, lyrics.ovh), embedded Vorbis/ID3 tags, AI genre categorization with Gemini and MusicBrainz, and studio album track repairs.

### 8. 💾 [Backups, Snapshots & Migration](backup-and-migration.md)
Learn how the engine protects your library state: hot zero-downtime SQLite snapshots using the WAL API, SHA-256 hash deduplication, single-file `.tar.gz` migration bundles, and restoring onto another machine with automatic path rebasing.

### 9. ❓ [Troubleshooting & FAQ](troubleshooting.md)
Solutions to common issues: missing API keys, `ffmpeg` audio extraction problems, SQLite WAL busy locks, YouTube rate-limiting or age restrictions, mobile scrobble sync delays, and accidental purges.

### 10. 🏗️ [System Architecture & Internals](architecture.md)
Comprehensive technical overview for developers: Conveyor lifecycle state machine, SQLite database schema with indices, audio storage directory hierarchy, and module catalog detailing every class in `src/`.

---

<p align="center">
  <a href="../../README.md"><b>⬅ Return to Project README</b></a> • <a href="installation.md"><b>Next: Installation Guide ➡</b></a>
</p>
