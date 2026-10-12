# 📦 Step-by-Step Installation Guide

<p align="center">
  <img src="https://img.shields.io/badge/guide-installation-blue?style=for-the-badge&logo=git&logoColor=white" alt="Installation Guide">
  <img src="https://img.shields.io/badge/python-3.10%20to%203.14-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10 to 3.14">
  <img src="https://img.shields.io/badge/platform-Linux%20|%20macOS%20|%20WSL2-555?style=for-the-badge" alt="Platforms">
</p>

This guide walks you through setting up **Music Engine** from scratch on any modern Linux distribution, macOS, or Windows WSL2 environment.

---

## 📑 Table of Contents

- [System Prerequisites](#-system-prerequisites)
- [1. Operating System Packages](#1-operating-system-packages)
- [2. Clone the Repository](#2-clone-the-repository)
- [3. Python Virtual Environment (.venv)](#3-python-virtual-environment-venv)
- [4. Install Python Dependencies](#4-install-python-dependencies)
- [5. Verify System Setup](#5-verify-system-setup)
- [6. Next Steps: Configuration](#6-next-steps-configuration)
- [Common Installation Pitfalls](#-common-installation-pitfalls)

---

## 🛠️ System Prerequisites

Music Engine requires:
1. **Python 3.10 or newer** (tested on 3.10, 3.11, 3.12, 3.13, and 3.14).
2. **ffmpeg** installed on the host system (required by `yt-dlp` to extract and transcode audio to Opus/M4A).
3. **Git** for version control.
4. **Internet connection** for initial setup, downloading audio, lyrics, and metadata.

---

## 1. Operating System Packages

Install Python, pip, virtual environment tools, and ffmpeg using your distribution's package manager:

### 🐧 Debian / Ubuntu / Linux Mint / Pop!_OS
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg git
```
> [!IMPORTANT]
> On Debian and Ubuntu systems, `python3-venv` is packaged separately from Python. Ensure it is explicitly installed to avoid `ensurepip` errors.

### 🏹 Arch Linux / Manjaro / EndeavourOS
```bash
sudo pacman -Syu --needed python python-pip ffmpeg git
```

### 🎩 Fedora / RHEL / AlmaLinux / Rocky Linux
```bash
sudo dnf install -y python3 python3-pip ffmpeg ffmpeg-free git
```

### 🦎 openSUSE (Tumbleweed / Leap)
```bash
sudo zypper refresh
sudo zypper install -y python3 python3-pip ffmpeg git
```

### 🏔️ Alpine Linux
```bash
apk update
apk add python3 py3-pip ffmpeg git
```

### 🍎 macOS (Homebrew)
```bash
brew install python ffmpeg git
```

### 🪟 Windows (WSL2)
Music Engine is designed for POSIX environments. On Windows, install **WSL2** with Ubuntu:
```powershell
# In PowerShell (Administrator):
wsl --install -d Ubuntu
```
Once inside the Ubuntu shell, follow the [Debian / Ubuntu instructions](#-debian--ubuntu--linux-mint--pop_os) above.

---

## 2. Clone the Repository

Clone the project repository to your desired location (e.g., inside `~/Projects` or `~/Music_Engine`):

```bash
git clone https://github.com/your-username/Music_Engine.git
cd Music_Engine
```

---

## 3. Python Virtual Environment (`.venv`)

Always isolate the engine's dependencies inside a dedicated virtual environment:

```bash
# 1. Create the virtual environment
python3 -m venv .venv

# 2. Activate the virtual environment
source .venv/bin/activate
```

> [!TIP]
> After activation, your shell prompt will show `(.venv)`. Whenever you open a new terminal to run commands manually, remember to run `source .venv/bin/activate` or use `.venv/bin/python main.py <command>`.

---

## 4. Install Python Dependencies

With the virtual environment activated, upgrade pip and install all required libraries:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Core Dependencies Overview

| Package | Minimum Version | Purpose |
| :--- | :--- | :--- |
| `yt-dlp` | `>=2024.08.06` | High-fidelity audio extraction and streaming. |
| `ytmusicapi` | `>=1.7.0` | YouTube Music catalog search, album heuristics and tracklists. |
| `google-genai` | `>=0.3.0` | Google Gemini AI SDK for taste curation and genre analysis. |
| `mutagen` | `>=1.47.0` | Audio tag injection (Vorbis, ID3, MP4) and cover art. |
| `thefuzz` | `>=0.22.1` | Fuzzy matching for scrobble reconciliation and order commands. |
| `filelock` | `>=3.15.4` | Process synchronization and concurrency safety (`engine.lock`). |
| `syncedlyrics`| `>=1.0.1` | Multi-provider synchronized lyrics scraper. |
| `pyyaml` | `>=6.0.1` | YAML configuration parser (`config.yaml`). |
| `python-dotenv` | `>=1.0.1` | Secure environment variable loader (`.env`). |

---

## 5. Verify System Setup

Run these quick checks to verify that external binaries and libraries are correctly wired up:

### Check ffmpeg
```bash
ffmpeg -version | head -n 1
```
*Expected: Version information (e.g., `ffmpeg version 6.x` or `7.x`).*

### Check Python & Virtual Environment
```bash
python -c "import mutagen, yt_dlp, ytmusicapi; print('✓ Core modules successfully loaded')"
```
*Expected: `✓ Core modules successfully loaded`.*

---

## 6. Next Steps: Configuration

Your environment is ready! Proceed to configure your storage paths, API credentials, and taste profile:

👉 **[Go to Configuration Guide](configuration.md)**

---

## ❓ Common Installation Pitfalls

### `ModuleNotFoundError: No module named 'venv'`
- **Cause:** On Debian/Ubuntu, `python3-venv` is an independent package.
- **Fix:** Run `sudo apt install python3-venv`.

### `externally-managed-environment` (PEP 668)
- **Cause:** Modern Linux distributions prevent running `pip install` directly into system Python to prevent breaking OS packages.
- **Fix:** Never use `sudo pip install`. Always create and activate a virtual environment (`python3 -m venv .venv` and `source .venv/bin/activate`).

### `ffmpeg not found in PATH`
- **Cause:** ffmpeg is either not installed or located in a custom directory not in your system `$PATH`.
- **Fix:** Check where ffmpeg is installed (`which ffmpeg`) and install it via your OS package manager.

---

<p align="center">
  <a href="README.md"><b>⬅ Docs Portal</b></a> • <a href="configuration.md"><b>Next: Configuration Guide ➡</b></a>
</p>
