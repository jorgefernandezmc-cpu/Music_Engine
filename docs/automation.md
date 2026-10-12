# ⏰ Background Automation (Systemd)

<p align="center">
  <img src="https://img.shields.io/badge/service-systemd_user-teal?style=for-the-badge&logo=linux&logoColor=white" alt="Systemd User">
  <img src="https://img.shields.io/badge/automation-unattended-brightgreen?style=for-the-badge" alt="Unattended Automation">
</p>

Music Engine is designed to run autonomously in the background on your Linux PC. Using **systemd user services and timers**, the engine can execute daily maintenance cycles, sync mobile telemetry, fetch requested songs, rotate discovery buffers, and clean unplayed tracks without requiring root privileges or manual intervention.

---

## 📑 Table of Contents

- [Why Systemd User Units?](#why-systemd-user-units)
- [1. Create the Service Unit (`music-engine.service`)](#1-create-the-service-unit-music-engineservice)
- [2. Create the Timer Unit (`music-engine.timer`)](#2-create-the-timer-unit-music-enginetimer)
- [3. Enable and Activate Automation](#3-enable-and-activate-automation)
- [4. Managing and Monitoring Service Runs](#4-managing-and-monitoring-service-runs)
- [5. Systemd Lingering (Run Even When Logged Out)](#5-systemd-lingering-run-even-when-logged-out)
- [6. Log Management & Logrotate](#6-log-management--logrotate)
- [Alternative: Classic Cronjob Setup](#alternative-classic-cronjob-setup)

---

## Why Systemd User Units?

- **Non-Root Execution:** Runs under your normal user account; files are created with correct ownership and permissions.
- **Desktop Notifications:** Easily interacts with user sessions to emit non-blocking `notify-send` desktop popups.
- **Environment Isolation:** Safely invokes the Python virtual environment (`.venv`).
- **Persistent Timers:** If your computer was asleep or turned off when the scheduled timer triggered, systemd runs the missed job immediately upon waking up.

---

## 1. Create the Service Unit (`music-engine.service`)

Create directory for user units if it does not already exist:

```bash
mkdir -p ~/.config/systemd/user
```

Create `~/.config/systemd/user/music-engine.service`:

```ini
[Unit]
Description=Music Engine Autonomous Cycle Runner
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
# Adjust WorkingDirectory to the absolute path of your repository:
WorkingDirectory=/home/YOUR_USERNAME/Projects/Music_Engine

# Invokes Python inside your virtual environment directly:
ExecStart=/home/YOUR_USERNAME/Projects/Music_Engine/.venv/bin/python main.py run

# Output and audit logging:
StandardOutput=append:/home/YOUR_USERNAME/Projects/Music_Engine/logs/systemd.log
StandardError=append:/home/YOUR_USERNAME/Projects/Music_Engine/logs/systemd.log

[Install]
WantedBy=default.target
```

> [!IMPORTANT]
> Replace `/home/YOUR_USERNAME/Projects/Music_Engine` with the actual path to your `Music_Engine` installation directory (run `pwd` inside the project folder to check).

---

## 2. Create the Timer Unit (`music-engine.timer`)

Create `~/.config/systemd/user/music-engine.timer`:

```ini
[Unit]
Description=Daily autonomous execution timer for Music Engine

[Timer]
# Runs every morning at 04:00 AM local time:
OnCalendar=*-*-* 04:00:00

# Catch up missed executions if the machine was powered off:
Persistent=true

# Add a small random jitter to prevent hitting APIs at exact millisecond marks:
RandomizedDelaySec=120

[Install]
WantedBy=timers.target
```

> [!TIP]
> **Need multiple runs per day?** You can set `OnCalendar=*-*-* 04,16:00:00` to run twice daily (at 4:00 AM and 4:00 PM), or `OnCalendar=hourly` to poll the requests mailbox every hour.

---

## 3. Enable and Activate Automation

Reload the systemd user daemon and start the timer:

```bash
# 1. Reload systemd user daemon
systemctl --user daemon-reload

# 2. Enable and start timer immediately
systemctl --user enable --now music-engine.timer
```

Verify that the timer is armed:

```bash
systemctl --user list-timers --all | grep music-engine
```

*Expected output:*
```text
NEXT                         LEFT          LAST PASSED UNIT                ACTIVATES
Tue 2026-10-13 04:00:00 CEST 8h left       n/a  n/a    music-engine.timer  music-engine.service
```

---

## 4. Managing and Monitoring Service Runs

### Trigger a Run Manually
You can test the systemd service anytime without waiting for the timer:

```bash
systemctl --user start music-engine.service
```

### Check Service Status
```bash
systemctl --user status music-engine.service
```

### Follow Logs in Real Time
```bash
# View combined systemd output:
tail -f logs/systemd.log

# View specific component logs:
tail -f logs/engine.log
tail -f logs/downloader.log
tail -f logs/curator.log
```

---

## 5. Systemd Lingering (Run Even When Logged Out)

If Music Engine runs on a home server, Raspberry Pi, or media PC where you are not actively logged into a graphical desktop session, enable **user lingering**:

```bash
sudo loginctl enable-linger $USER
```

This instructs systemd to keep your user service manager running 24/7 from system boot to shutdown.

---

## 6. Log Management & Logrotate

To prevent log files in `logs/` from growing indefinitely over months of operation, you can configure a user logrotate rule:

Create `~/.config/logrotate.d/music-engine`:

```text
/home/YOUR_USERNAME/Projects/Music_Engine/logs/*.log {
    weekly
    rotate 4
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
```

---

## 🔄 Alternative: Classic Cronjob Setup

If your Linux environment does not use systemd (e.g. Alpine Linux, Docker container, or minimalist BSD environments), you can schedule the engine using standard user cron:

```bash
crontab -e
```

Add the following line:

```cron
0 4 * * * cd /home/YOUR_USERNAME/Projects/Music_Engine && .venv/bin/python main.py run >> logs/systemd.log 2>&1
```

---

<p align="center">
  <a href="mobile-and-sync.md"><b>⬅ Mobile & Sync</b></a> • <a href="metadata-and-lyrics.md"><b>Next: Metadata, Genres & Lyrics ➡</b></a>
</p>
