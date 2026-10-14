# ❓ Troubleshooting & Frequently Asked Questions (FAQ)

<p align="right">
  <b>Language / Idioma:</b>
  <b>🇬🇧 English</b> | <a href="../es/troubleshooting.md">🇪🇸 Español</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/guide-troubleshooting_&_faq-red?style=for-the-badge&logo=shield&logoColor=white" alt="Troubleshooting">
  <img src="https://img.shields.io/badge/status-solutions-green?style=for-the-badge" alt="Solutions">
</p>

This guide addresses common error messages, system configuration pitfalls, edge cases, and operational questions encountered while running **Music Engine**.

---

## 📑 Table of Contents

- [Quick Diagnostic Commands](#-quick-diagnostic-commands)
- [Common Error Messages & Fixes](#-common-error-messages--fixes)
  - [`ERROR: Critical environment variables missing in config/.env`](#1-error-critical-environment-variables-missing-in-configenv)
  - [`sqlite3.OperationalError: database is locked`](#2-sqlite3operationalerror-database-is-locked)
  - [`FileLockTimeout: Could not acquire lock data/engine.lock`](#3-filelocktimeout-could-not-acquire-lock-dataenginelock)
  - [`ffmpeg: command not found` / yt-dlp Transcoding Failures](#4-ffmpeg-command-not-found--yt-dlp-transcoding-failures)
  - [`Sign in to confirm you’re not a bot` / YouTube 429 Errors](#5-sign-in-to-confirm-youre-not-a-bot--youtube-429-errors)
- [Lifecycle & Library Behavior FAQ](#-lifecycle--library-behavior-faq)
  - [Why are songs in Conveyor being purged earlier than expected?](#why-are-songs-in-conveyor-being-purged-earlier-than-expected)
  - [Why is a song not promoting to Permanent after multiple plays?](#why-is-a-song-not-promoting-to-permanent-after-multiple-plays)
  - [Can I prevent a specific song from ever being deleted?](#can-i-prevent-a-specific-song-from-ever-being-deleted)
- [Mobile & Sync FAQ](#-mobile--sync-faq)
  - [Syncthing creates `.sync-conflict` files](#syncthing-creates-sync-conflict-files)
  - [Lune player doesn't show updated playlists](#lune-player-doesnt-show-updated-playlists)
  - [Pano Scrobbler is not uploading plays to ListenBrainz](#pano-scrobbler-is-not-uploading-plays-to-listenbrainz)
- [Systemd & Automation FAQ](#-systemd--automation-faq)
  - [Desktop notifications (`notify-send`) not appearing](#desktop-notifications-notify-send-not-appearing)
  - [Systemd user timer does not run when logged out](#systemd-user-timer-does-not-run-when-logged-out)

---

## 🩺 Quick Diagnostic Commands

Run these health checks before deep troubleshooting:

```bash
# 1. Check database connectivity and track counters:
python main.py status

# 2. Check ffmpeg availability:
ffmpeg -version | head -n 1

# 3. Test Gemini API connectivity:
python -c "from dotenv import load_dotenv; import os, google.genai as genai; load_dotenv('config/.env'); client = genai.Client(api_key=os.getenv('GEMINI_API_KEY')); print('✓ Gemini API connected!')"

# 4. Check systemd timer status (Linux):
systemctl --user status music-engine.timer

# 5. Inspect the latest 50 lines of logs:
tail -n 50 logs/engine.log
```

---

## ⚠️ Common Error Messages & Fixes

### 1. `ERROR: Critical environment variables missing in config/.env`
- **Cause:** `GEMINI_API_KEY` is empty, unset, or still contains default placeholder text.
- **Fix:**
  1. Open `config/.env`.
  2. Ensure `GEMINI_API_KEY=AIzaSy...` has a valid key obtained from [Google AI Studio](https://aistudio.google.com/).
  3. Avoid surrounding the key with extraneous quotes or spaces.

---

### 2. `sqlite3.OperationalError: database is locked`
- **Cause:** Another process or external SQLite browser (like DB Browser for SQLite) has an open uncommitted write transaction.
- **Fix:**
  1. Close any external database GUI viewing `data/conveyor_state.sqlite`.
  2. Check for lingering Python processes:
     ```bash
     ps aux | grep "main.py"
     ```
  3. Force a WAL checkpoint:
     ```bash
     python -c "import sqlite3; conn = sqlite3.connect('data/conveyor_state.sqlite'); conn.execute('PRAGMA wal_checkpoint(TRUNCATE);'); conn.close(); print('✓ Checkpoint forced')"
     ```

---

### 3. `FileLockTimeout: Could not acquire lock data/engine.lock`
- **Cause:** The previous engine run crashed or was forcefully killed (`kill -9`), leaving a stale lockfile behind.
- **Fix:**
  1. Verify no engine instance is currently running: `pgrep -f "python.*main.py"`.
  2. If none are running, safely remove the lockfile:
     ```bash
     rm -f data/engine.lock
     ```

---

### 4. `ffmpeg: command not found` / `yt-dlp` Transcoding Failures
- **Cause:** `yt-dlp` requires `ffmpeg` to extract raw audio from video containers and convert them to Opus or M4A.
- **Fix:** Install ffmpeg for your operating system:
  ```bash
  # Ubuntu / Debian:
  sudo apt install ffmpeg

  # Arch Linux:
  sudo pacman -S ffmpeg

  # Fedora:
  sudo dnf install ffmpeg ffmpeg-free

  # macOS:
  brew install ffmpeg
  ```

---

### 5. `Sign in to confirm you’re not a bot` / YouTube 429 Errors
- **Cause:** YouTube rate-limited anonymous download requests or the track requires age verification.
- **Fix:**
  1. Install a browser extension (such as *Get cookies.txt LOCALLY*) in Chrome/Firefox.
  2. Log in to YouTube in your browser.
  3. Export cookies in Netscape format and save as `config/cookies.txt`.
  4. Music Engine automatically loads `config/cookies.txt` whenever present.

---

## 🔄 Lifecycle & Library Behavior FAQ

### Why are songs in Conveyor being purged earlier than expected?
Check the following rules in `config/config.yaml`:
1. **`grace_period_days` (default: 150):** If you haven't played a song in 150 days, the Guillotine assumes you don't like it and purges it to free space. Increase this to `365` if you want a longer window.
2. **`max_skips_before_purge` (default: 5) & `max_skip_ratio` (default: 0.7):** If you frequently skip a track without listening to completion, the engine treats it as a negative signal and removes it.
3. **Telemetry Margin:** If `telemetry_safety_margin_days` (default: 7) has passed without a successful ListenBrainz sync, the engine suspends all purges automatically as a safety measure.

### Why is a song not promoting to Permanent after multiple plays?
1. **Scrobbles not reaching PC:** Ensure Pano Scrobbler is synced with ListenBrainz and you have run `python main.py sync-telemetry` or `python main.py run`.
2. **Play threshold:** The default threshold is `promotion_play_count: 15`. You can adjust this to `5` or `10` in `config/config.yaml` under `conveyor.promotion_play_count`.
3. **Title mismatch:** If the mobile player tags differ significantly from YouTube Music metadata, check `orphan_scrobbles` table in SQLite.

### Can I prevent a specific song from ever being deleted?
**Yes!** Choose any of these methods:
- Tap the **❤️ Heart / Love** icon in your mobile player.
- Add `favorite: Track Name` or `permanent: Track Name` to `requests.txt`.
- Run `python main.py set-album "<Track>" "<Album>"`.

---

## 📱 Mobile & Sync FAQ

### Syncthing creates `.sync-conflict` files
- **Cause:** Simultaneous edits on both phone and PC to the same file (typically `requests.txt` or `.m3u8` playlists).
- **Fix:**
  1. Ensure `.stignore` is present in your root music folder (see [Mobile Ecosystem Guide](mobile-and-sync.md)).
  2. Delete leftover `.sync-conflict` files:
     ```bash
     find ~/Music/Songs -name "*.sync-conflict-*" -delete
     ```

### Lune player doesn't show updated playlists
- **Cause:** Android restricts direct indexing of `.m3u8` files. Lune relies on JSON backups.
- **Fix:**
  1. Ensure `generate_lune_backup: true` is enabled in `config/config.yaml`.
  2. In Lune on Android, go to **Settings** $\rightarrow$ **Import playlists** $\rightarrow$ Select `Playlists/lune_playlists_backup.json`.

### Pano Scrobbler is not uploading plays to ListenBrainz
- **Cause:** Android battery optimization killed Pano Scrobbler in the background.
- **Fix:**
  1. On Android: **Settings** $\rightarrow$ **Apps** $\rightarrow$ **Pano Scrobbler** $\rightarrow$ **Battery** $\rightarrow$ Set to **Unrestricted**.
  2. Ensure **Notification Access** is granted to Pano Scrobbler.

---

## ⏰ Systemd & Automation FAQ

### Desktop notifications (`notify-send`) not appearing
- **Cause:** The systemd user service might not have access to the graphical display environment variable (`$DBUS_SESSION_BUS_ADDRESS`).
- **Fix:**
  The notification module (`src/notifications.py`) detects headless environments and fails gracefully without raising exceptions. For graphical notifications:
  ```bash
  systemctl --user import-environment DISPLAY WAYLAND_DISPLAY DBUS_SESSION_BUS_ADDRESS
  ```

### Systemd user timer does not run when logged out
- **Cause:** By default, systemd stops user managers when the last user session logs out.
- **Fix:** Enable user lingering:
  ```bash
  sudo loginctl enable-linger $USER
  ```

---

<p align="center">
  <a href="backup-and-migration.md"><b>⬅ Backups & Migration</b></a> • <a href="architecture.md"><b>Next: System Architecture ➡</b></a>
</p>
