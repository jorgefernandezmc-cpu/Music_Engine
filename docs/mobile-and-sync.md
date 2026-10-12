# 📲 Mobile Ecosystem & Synchronization

<p align="center">
  <img src="https://img.shields.io/badge/integration-Android_&_Syncthing-16A085?style=for-the-badge&logo=syncthing&logoColor=white" alt="Syncthing">
  <img src="https://img.shields.io/badge/telemetry-ListenBrainz-EB743B?style=for-the-badge&logo=musicbrainz&logoColor=white" alt="ListenBrainz">
  <img src="https://img.shields.io/badge/player-Lune_%7C_Auxio_%7C_Symfonium-purple?style=for-the-badge" alt="Players">
</p>

Music Engine is designed for an **offline-first mobile experience**. All your music, lyrics, playlists, and commands synchronize bidirectionally between your Linux PC and Android devices without reliance on proprietary streaming clouds.

---

## 📑 Table of Contents

- [Mobile Ecosystem Architecture](#-mobile-ecosystem-architecture)
- [1. Syncthing Setup (P2P File Synchronization)](#1-syncthing-setup-p2p-file-synchronization)
  - [Install Syncthing](#install-syncthing)
  - [Folder Pairing](#folder-pairing)
  - [Recommended .stignore](#recommended-stignore)
- [2. Mobile Music Players & Playlists](#2-mobile-music-players--playlists)
  - [Universal .m3u8 Playlists](#universal-m3u8-playlists)
  - [Lune Android Player Integration](#lune-android-player-integration)
  - [User-Created Playlists from Mobile](#user-created-playlists-from-mobile)
  - [Synchronized Lyrics (.lrc) Display](#synchronized-lyrics-lrc-display)
- [3. Telemetry Feedback Loop (Pano Scrobbler + ListenBrainz)](#3-telemetry-feedback-loop-pano-scrobbler--listenbrainz)
  - [Setup Pano Scrobbler on Android](#setup-pano-scrobbler-on-android)
  - [How Scrobbles Trigger Promotions](#how-scrobbles-trigger-promotions)
  - [Heart Shielding (Loved Tracks)](#heart-shielding-loved-tracks)

---

## 📐 Mobile Ecosystem Architecture

```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │                         ANDROID MOBILE PHONE                           │
 │                                                                        │
 │  [ Lune / Auxio / Symfonium ] ──▶ [ Pano Scrobbler ] ──▶ [ListenBrainz]│
 │          ▲                                |                 (Cloud)    │
 └──────────┼────────────────────────────────┼────────────────────┼───────┘
            │                                │                    │
            │ Audio files, .lrc sidecars     │ Offline & Online   │
            │ & requests.txt                 │ Scrobbles + Hearts │
            ▼                                │                    │
   ═══ [ SYNCTHING ] ═══                     │                    │
            ▲                                │                    │
 ┌──────────┼────────────────────────────────┼────────────────────┼───────┘
 │          ▼                                ▼                    ▼       │
 │   storage.base_dir                  Heart Feedback        Scrobbles    │
 │   (/home/user/Music/Songs)                │                    │       │
 │          │                                └─────────┬──────────┘       │
 │          ▼                                          ▼                  │
 │  ┌─────────────────────────────────────────────────────────────────┐   │
 │  │                         MUSIC ENGINE (PC)                       │   │
 │  │  • FileSyncManager   • TelemetryEngine   • OrderProcessor       │   │
 │  │  • Downloader        • LyricsProvider    • PlaylistGenerator    │   │
 │  └─────────────────────────────────────────────────────────────────┘   │
 │                               LINUX PC                                 │
 └────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Syncthing Setup (P2P File Synchronization)

[Syncthing](https://syncthing.net/) provides decentralized, encrypted, continuous file synchronization over your local Wi-Fi network and the internet.

### Install Syncthing

1. **On your PC (Linux):**
   ```bash
   # Debian / Ubuntu:
   sudo apt install syncthing
   systemctl --user enable --now syncthing

   # Arch Linux:
   sudo pacman -S syncthing
   systemctl --user enable --now syncthing
   ```
2. **On Android:**
   - Install **Syncthing-Fork** from [F-Droid](https://f-droid.org/packages/com.github.catfriend1.syncthingandroid/) or Google Play Store.

### Folder Pairing

1. Access the Syncthing Web UI on your PC (`http://127.0.0.1:8384`).
2. Add your Android device using its Device ID or QR Code.
3. Share your music base directory (the one defined as `storage.base_dir` in `config/config.yaml`, e.g., `~/Music/Songs`).
4. On your phone, accept the shared folder and choose a local directory on your internal storage or SD card (e.g., `Music/Songs`).
5. Set Folder Type to **Send & Receive** on both devices.

### Recommended `.stignore`

Inside the root of your shared music folder on PC, create a file named `.stignore` to prevent syncing temporary files, locks, and cache:

```text
(?d).venv*
(?d)__pycache__
(?d)*.pyc
(?d)*.lock
(?d)*.tmp
(?d).stversions
(?d).DS_Store
```

---

## 2. Mobile Music Players & Playlists

### Universal `.m3u8` Playlists

Music Engine automatically generates standard, UTF-8 formatted `.m3u8` playlists in `Playlists/`:

| Playlist File | Contents & Behavior |
| :--- | :--- |
| `Permanent.m3u8` | Entire permanent collection organized by Artist $\rightarrow$ Album $\rightarrow$ Track. |
| `Conveyor.m3u8` | All tracks currently rotating in the Conveyor discovery buffer. |
| `Priority_Discovery.m3u8` | Newly downloaded discoveries waiting for their very first play. |
| `Live_Rotation.m3u8` | Dynamic mix: most-played tracks + fresh discoveries + forgotten gems. |
| `Cravings.m3u8` | Tracks in the temporary Cravings collection. |
| `Artistas/<Artist>.m3u8` | Comprehensive playlist for each artist meeting the track threshold (default: 10 tracks). |

These playlists are compatible out of the box with:
- **Auxio** (Clean, open-source Android player)
- **Symfonium** (Feature-packed local & network music player)
- **Retro Music Player**
- **Musicolet**
- **Poweramp**
- **VLC for Android**

---

### Lune Android Player Integration

[Lune](https://github.com/) is a modern, lightweight, privacy-focused offline music player for Android.

Because Android 11+ restricts file indexing for raw playlist files, Lune uses an internal SQLite database. Music Engine includes **native bidirectional integration** with Lune:

1. In `config/config.yaml`, ensure:
   ```yaml
   playlists:
     generate_lune_backup: true
     lune_backup_file: "lune_playlists_backup.json"
     user_playlists_dir: "Listas Propias"
   ```
2. When the engine runs, it compiles and syncs `Playlists/lune_playlists_backup.json`.
3. In Lune on your phone:
   - Navigate to **Settings** $\rightarrow$ **Import playlists**.
   - Select `Playlists/lune_playlists_backup.json`.
   - All your system playlists, artist playlists, and user playlists will be loaded into Lune instantly!

---

### User-Created Playlists from Mobile

You can create custom playlists inside Lune directly on your phone:
1. Create a playlist in Lune (e.g., *"Gym Energy"* or *"Roadtrip"*).
2. Export your playlists in Lune: **Settings** $\rightarrow$ **Export playlists** $\rightarrow$ Save as `lune_playlists_backup.json` in your synced `Playlists/` folder.
3. When Syncthing transfers this file to your PC, Music Engine:
   - Extracts your custom playlists into `Playlists/Listas Propias/<Playlist>.m3u8`.
   - Resolves all track titles against your local library files.
   - Cleans ghost tracks (songs you previously deleted or purged).
   - Keeps your user-created playlists preserved across backup exports.

---

### Synchronized Lyrics (`.lrc`) Display

Music Engine embeds lyrics into Vorbis/MP4 tags **and** places contiguous `.lrc` sidecars alongside every audio file:
```text
Permanent/Daft Punk/Discovery/Daft Punk - One More Time.opus
Permanent/Daft Punk/Discovery/Daft Punk - One More Time.lrc
```

Whenever you play a track in **Lune**, **Auxio**, or **Symfonium**, synchronized karaoke-style lyrics light up automatically with millisecond precision without needing an active internet connection.

---

## 3. Telemetry Feedback Loop (Pano Scrobbler + ListenBrainz)

To enable automatic promotion and smart pruning, Music Engine tracks your real listening habits through **ListenBrainz**.

### Setup Pano Scrobbler on Android

1. Install [Pano Scrobbler](https://github.com/kawaiiDango/pno-scrobbler) from F-Droid or Google Play Store.
2. Grant Notification Access permission (required to detect music playback).
3. Under **Scrobbling Services**, select **ListenBrainz** and log in with your account.
4. Enable **Offline Scrobbling**: Pano Scrobbler records every song you listen to—even while hiking in airplane mode—and uploads scrobbles once Wi-Fi or data reconnects.

### How Scrobbles Trigger Promotions

1. When you listen to a track on your phone, Pano Scrobbler logs a scrobble.
2. During the next PC engine cycle (`main.py run` or `sync-telemetry`):
   - The engine queries ListenBrainz for your recent scrobbles.
   - Using fuzzy title/artist matching, it matches scrobbles against your local tracks.
   - It updates `play_count` and `last_played_at`.
3. If a track in the **Conveyor** buffer reaches the promotion threshold (default: 15 plays):
   - The engine promotes it to **Permanent**.
   - It resolves the canonical studio album.
   - It physically moves audio and `.lrc` files to `Permanent/<Artist>/<Album>/`.

### Heart Shielding (Loved Tracks)

In your mobile player or through Pano Scrobbler's notification bar, tap the **❤️ Heart / Love** icon on any song.

On the next sync, the engine:
1. Detects that the track was marked as "Loved" on ListenBrainz.
2. **Immediately shields it from the Guillotine**.
3. Promotes it to `Permanent/` regardless of its play count.

---

<p align="center">
  <a href="mailbox-commands.md"><b>⬅ Remote Mailbox</b></a> • <a href="automation.md"><b>Next: Background Automation ➡</b></a>
</p>
