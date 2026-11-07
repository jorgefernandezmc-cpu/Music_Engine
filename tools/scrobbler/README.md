# 🎧 MPRIS Offline-Resilient Scrobbler Daemon

A lightweight, resilient Linux background scrobbler designed to guarantee that **no song playback is ever lost**, whether listening online, offline, traveling, or across system reboots.

---

## 🌟 Why this daemon?

Standard Linux scrobblers (such as `rescrobbled` or `mpris-scrobbler`) send scrobbles directly over HTTP at the exact moment a track finishes. If your laptop has no Wi-Fi, DNS fails, or you are offline, standard scrobblers simply discard the song and drop the scrobble forever.

This daemon introduces a **persistent local SQLite queue** (similar to Android's *Pano Scrobbler*):
1. **Listens to MPRIS D-Bus** in real-time (WaveFlow, Spotify, browsers, MPD, etc.).
2. **Tracks song progression** using standard industry thresholds (50% of track or 240s, configurable minimum floor).
3. **Stores qualified tracks immediately** into a local SQLite database (`data/scrobbler_queue.sqlite`).
4. **Flushes automatically in batches** to [ListenBrainz](https://listenbrainz.org) whenever network is available, preserving the exact original timestamp (`listened_at`).
5. **Completely offline-tolerant**: Starts cleanly without network, survives Wi-Fi drops, and catches up smoothly once reconnected.

---

## ⚙️ Configuration

In your `config/config.yaml`:

```yaml
scrobbler:
  # Enable or disable the scrobbler:
  enabled: true

  # Minimum listening duration (seconds) required before qualifying:
  min_play_time: 45

  # Percentage of song duration required (0.50 = 50%):
  completion_ratio: 0.50

  # Whitelist of player bus names (supports regex).
  # Use [] or ["*"] to scrobble from all players, or filter to specific players:
  player_whitelist:
    - "waveflow"

  # Path to the persistent SQLite queue file:
  queue_db: "data/scrobbler_queue.sqlite"
```

Credentials (`LISTENBRAINZ_TOKEN` and `LISTENBRAINZ_USER`) are automatically loaded from `config/.env` or system environment variables.

---

## 🚀 Quick Usage

### Check pending scrobbles in offline queue:
```bash
python main.py scrobbler --status
```

### Force immediate queue flush to ListenBrainz:
```bash
python main.py scrobbler --flush
```

### Run daemon interactively:
```bash
python main.py scrobbler
```

---

## 🐧 Installing as a Systemd User Service

To have the scrobbler start automatically on login and run reliably in the background:

1. **Copy the service file to your systemd user directory:**
   ```bash
   mkdir -p ~/.config/systemd/user
   cp tools/scrobbler/music-scrobbler.service ~/.config/systemd/user/
   ```

2. **Reload systemd and enable the service:**
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now music-scrobbler.service
   ```

3. **Check live status & logs:**
   ```bash
   systemctl --user status music-scrobbler.service
   journalctl --user -u music-scrobbler.service -f
   ```

If you previously used `rescrobbled`, you can disable it:
```bash
systemctl --user disable --now rescrobbled.service
```
