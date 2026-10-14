# 📱 Remote Control Mailbox (`requests.txt` / `peticiones.txt`)

<p align="right">
  <b>Language / Idioma:</b>
  <b>🇬🇧 English</b> | <a href="../es/mailbox-commands.md">🇪🇸 Español</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/feature-remote_mailbox-purple?style=for-the-badge&logo=fastapi&logoColor=white" alt="Remote Mailbox">
  <img src="https://img.shields.io/badge/bilingual-English%20and%20Spanish-orange?style=for-the-badge" alt="Bilingual">
</p>

The **Remote Control Mailbox** allows you to send instructions, download full albums, paste direct URLs from YouTube or Spotify, fix songs with mismatched audio, manage personal playlists, or inspect track metadata directly from your smartphone without opening a terminal or connecting via SSH.

---

## 📑 Table of Contents

- [How the Mailbox Works](#-how-the-mailbox-works)
- [Command Syntax Summary Table](#-command-syntax-summary-table)
- [1. Full Studio Album Downloads](#1-full-studio-album-downloads)
- [2. Individual Track Downloads](#2-individual-track-downloads)
- [3. Direct URL Downloads (YouTube, YT Music, Spotify)](#3-direct-url-downloads-youtube-yt-music-spotify)
- [4. Temporary Cravings Buffer](#4-temporary-cravings-buffer)
- [5. Audio Repair and Replacement (Auto-Fix and Manual URL)](#5-audio-repair-and-replacement-auto-fix-and-manual-url)
- [6. Promotion and Shielding to Permanent](#6-promotion-and-shielding-to-permanent)
- [7. Discarding and Purging Songs (Conveyor and Permanent Collection)](#7-discarding-and-purging-songs-conveyor-and-permanent-collection)
- [8. Reassigning Metadata, Albums, and Artists](#8-reassigning-metadata-albums-and-artists)
- [9. Personal Playlist Management](#9-personal-playlist-management)
- [10. Inspecting Track Information (Info)](#10-inspecting-track-information-info)
- [11. Forcing Clean Track Re-downloads](#11-forcing-clean-track-re-downloads)
- [12. Music Genre Correction](#12-music-genre-correction)
- [13. Updating Synchronized Lyrics](#13-updating-synchronized-lyrics)
- [14. Discovery Themed Radios](#14-discovery-themed-radios)
- [Feedback Loop and Error Reporting](#-feedback-loop-and-error-reporting)

---

## 📬 How the Mailbox Works

```text
 ┌────────────────┐          Syncthing          ┌────────────────┐
 │ Mobile Device  │  ─────────────────────────▶ │  Music Engine  │
 │ (Notes App)    │  ◀───────────────────────── │  (Background)  │
 └────────────────┘                             └────────────────┘
         │                                              │
         ▼                                              ▼
 Edit requests.txt or                       Reads lines each cycle,
 peticiones.txt in the                      downloads audio/lyrics,
 synced folder                              clears finished orders, and
                                            reports info or errors
```

1. Inside your music base directory (`storage.base_dir`), open `requests.txt` (or `peticiones.txt`) using any text or notes editor on your smartphone.
2. Add your instructions at the bottom of the file (below the `#` commented tutorial header).
3. Save the file. **Syncthing** syncs it instantly with your computer.
4. On the next execution cycle (via `systemd` or by manually running `python main.py run`), the engine parses the commands, executes them, clears completed orders, inserts info results, and explains errors if any occurred.

> [!TIP]
> **Automatic Header Language Sync:** The instructional header at the top of `requests.txt` (or `peticiones.txt`) adapts automatically to your `system.language` setting (`"en"` or `"es"` in `config/config.yaml`). If you switch language, the header updates on the next cycle while preserving all your pending notes and orders untouched.

---

## 📋 Command Syntax Summary Table

The mailbox accepts syntax interchangeably in **English** and **Spanish**:

| Operation | English Syntax | Spanish Syntax | Target / Effect |
| :--- | :--- | :--- | :--- |
| **Permanent Album** | `album: Artist - Album`<br>`permanent album: Artist - Album` | `disco: Artista - Disco`<br>`permanente album: Artista - Disco` | `Permanent/<Artist>/<Album>/` |
| **Craving Album** | `craving album: Artist - Album` | `antojo album: Artista - Disco` | `Cravings/<Artist>/<Album>/` |
| **Permanent Track** | `permanent: Artist - Track`<br>`Download "Track" by Artist` | `permanente: Artista - Tema`<br>`Descargar "Tema" de Artista` | `Permanent/<Artist>/<Album>/` |
| **Craving Track** | `craving: Artist - Track` | `antojo: Artista - Tema` | `Cravings/<Artist>/<Album>/` |
| **Direct URL** | `https://music.youtube.com/...`<br>`url: https://...` | `https://music.youtube.com/...`<br>`url: https://...` | Direct download of track or playlist |
| **Craving URL** | `craving: https://...` | `antojo: https://...` | Downloads into temporary Cravings buffer |
| **Repair (Auto)** | `fix: Artist - Track`<br>`repair: Track` | `reparar: Artista - Tema`<br>`arreglar: Tema` | Searches official studio release on YT Music |
| **Repair (Manual URL)** | `fix: Track -> URL`<br>`repair: Track -> URL` | `reparar: Tema -> URL`<br>`fix: Tema -> URL` | Replaces audio with the exact provided URL |
| **Promote Track** | `favorite: Track`<br>`shield: Artist - Track` | `favorita: Tema`<br>`blindar: Artista - Tema` | Moves from Conveyor/Cravings to Permanent |
| **Purge from Conveyor** | `purge: Track`<br>`delete: Track` | `borrar: Tema`<br>`eliminar: Tema` | Deletes audio & `.lrc`, marks `PURGED` |
| **Purge from Permanent** | `purge permanent: Artist - Track`<br>`delete permanent: Track` | `borrar permanente: Artista - Tema`<br>`eliminar permanente: Tema` | Deletes from `Permanent/`, cleans dirs, marks `PURGED` |
| **Reassign Album** | `album: Track -> New Album` | `album: Tema -> Nuevo Álbum` | Moves files and tags to new album |
| **Reassign Artist** | `artist: Track -> New Artist` | `artista: Tema -> Nuevo Artista` | Moves files and updates artist tags |
| **Add to Playlist** | `playlist: Name += Track` | `lista: NombreLista += Tema` | Adds track to M3U8 playlist |
| **Remove from Playlist**| `playlist: Name -= Track` | `lista: NombreLista -= Tema` | Removes track from M3U8 playlist |
| **Force Re-download** | `redownload: Artist - Track` | `redescargar: Artista - Tema` | Cleans cache and re-downloads fresh audio |
| **Inspect Track Info** | `info: Artist - Track`<br>`information: Track` | `info: Artista - Tema`<br>`informacion: Tema` | Inserts commented technical breakdown |
| **Correct Genre** | `genre: Track -> New Genre`<br>`genre: Track` (AI auto) | `genero: Tema -> Nuevo Género`<br>`genero: Tema` | Injects tag into file and database |
| **Refresh Lyrics** | `lyrics: Track` | `letra: Tema` | Re-queries and stores synchronized `.lrc` |
| **Themed Radio** | `radio: Vibe Description` | `radio: Descripción de Estilo` | Populates Conveyor with vibe matches |

---

## 1. Full Studio Album Downloads

Download complete official tracklists directly from YouTube Music:

```text
# Download full album The Dark Side of the Moon to Permanent:
album: Pink Floyd - The Dark Side of the Moon

# Explicit permanent album syntax:
permanent album: Rosalía - Motomami

# Natural language:
Download the album "Random Access Memories" by Daft Punk
```

---

## 2. Individual Track Downloads

Download individual tracks directly into the permanent library with strict artist disambiguation:

```text
# Structured syntax with artist and title:
permanent: Daft Punk - Get Lucky
permanent: Kendrick Lamar - Not Like Us

# Natural language:
Download "Starboy" by The Weeknd
Download "Ojitos Lindos" by Bad Bunny
```

---

## 3. Direct URL Downloads (YouTube, YT Music, Spotify)

Tap **"Share link"** on your smartphone and paste the URL directly into the mailbox:

```text
# YouTube Music link to Permanent:
https://music.youtube.com/watch?v=5NV6Rdv1a3I

# Standard YouTube or short URL:
https://youtu.be/5NV6Rdv1a3I

# Explicit Craving link:
craving: https://music.youtube.com/watch?v=5NV6Rdv1a3I

# Full YouTube Music Playlist:
https://music.youtube.com/playlist?list=PLw-VjHDlEOgvtnnnqWlTqByAtC7tXBg6D

# Spotify link (resolves title & artist and downloads official audio):
https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT
```

---

## 4. Temporary Cravings Buffer

Seasonal hits or party tracks you want to enjoy for a few weeks without keeping permanently:

```text
# Single track craving:
craving: Charli xcx - Apple
antojo: Quevedo - Columbia

# Full album craving:
craving album: Arctic Monkeys - AM
antojo album: C. Tangana - El Madrileño
```

> [!NOTE]
> Cravings are automatically rotated and deleted after `cravings.retention_days` (default: 30 days). If you love a craving track, promote it to permanent at any time with `favorite: Track`.

---

## 5. Audio Repair and Replacement (Auto-Fix and Manual URL)

If a downloaded track has correct metadata but the audio is a live recording, low-quality rip, remix, or wrong track:

### Option A: Automatic Studio Version Search
The engine searches for the official studio version while explicitly ignoring the current bad video ID:

```text
fix: Pink Floyd - Comfortably Numb
reparar: Hotel California
repair: Daft Punk - Get Lucky
```

### Option B: Precise Replacement via Manual YouTube URL
If you want 100% exact control with a specific YouTube Music video or audio stream:

```text
fix: Daft Punk - Get Lucky -> https://music.youtube.com/watch?v=5NV6Rdv1a3I
reparar: Starboy -> https://youtu.be/34Na4j8AVgA
```

*Internal execution*: The engine deletes the old local audio and `.lrc`, removes the video ID from the download archive cache (`data/download_archive.txt`), updates the track record, and queues a fresh download.

---

## 6. Promotion and Shielding to Permanent

Promote a discovery from your **Conveyor** (Cinta) or **Cravings** buffer to your permanent library:

```text
favorite: Midnight City
shield: M83 - Midnight City
favorita: Daft Punk - Instant Crush
```

The engine resolves the canonical studio album, moves files and `.lrc` to `Permanent/<Artist>/<Album>/`, removes empty directories, and updates playlists.

---

## 7. Discarding and Purging Songs (Conveyor and Permanent Collection)

### Purging from Conveyor or Cravings
```text
purge: Song Name
delete: Song Name
borrar: Song Name
```
Deletes the file and marks the track as `PURGED` so the AI curator never downloads it again.

### Purging from the Permanent Collection
To prevent accidental deletions, purging permanent tracks requires explicit syntax:

```text
purge permanent: Queen - Bohemian Rhapsody
delete permanent: Daft Punk - One More Time
borrar permanente: Artist - Track
```
Physically removes the audio and lyrics from `Permanent/`, cleans up empty album/artist folders, and regenerates permanent playlists.

---

## 8. Reassigning Metadata, Albums, and Artists

### Reassigning Album
```text
album: Instant Crush -> Random Access Memories (10th Anniversary)
disco: Bohemian Rhapsody -> A Night at the Opera
```

### Reassigning Primary Artist
If a track was cataloged under a guest collaboration and you want it filed under the main artist:

```text
artist: Save Your Tears -> The Weeknd
artista: Cuica -> Rosalía
```
Moves files physically to `Permanent/<New Artist>/<Album>/`, updates file tags (`artist` / `©ART`), and rebuilds library indexes.

---

## 9. Personal Playlist Management

Add or remove songs from your custom playlists (`Playlists/Listas Propias/`):

```text
# Add to playlist:
playlist: Workout += Eye of the Tiger
lista: Favorites 2024 += Daft Punk - Get Lucky

# Remove from playlist:
playlist: Workout -= Eye of the Tiger
lista: Favorites 2024 -= Get Lucky
```

---

## 10. Inspecting Track Information (Info)

Type `info:` to have the engine inspect the database and physical file tags, inserting a technical summary in the mailbox:

```text
info: Daft Punk - Get Lucky
information: Bohemian Rhapsody
```

The engine responds at the bottom of the file with a commented breakdown:
```text
# --- TRACK INFORMATION (Results) ---
# [INFO] Daft Punk - Get Lucky | Album: Random Access Memories (2013) #8 | Genre: Disco / Funk | Status: PERMANENT | Duration: 4:09 | File: OPUS (5.2 MB) | Lyrics: Synced (.lrc)
```

---

## 11. Forcing Clean Track Re-downloads

If a downloaded file is corrupted or you want to re-download with updated settings:

```text
redownload: Daft Punk - One More Time
redescargar: Queen - Don't Stop Me Now
```
Deletes the existing audio and lyrics, clears the download archive cache, and queues a clean download.

---

## 12. Music Genre Correction

```text
# Direct manual assignment:
genre: Midnight City -> Synthwave / Dream Pop

# Re-analysis via AI:
genre: Midnight City
genero: Bohemian Rhapsody
```

---

## 13. Updating Synchronized Lyrics

Forces real-time lyrics download across LRCLIB, Syncedlyrics, and YouTube Music:

```text
lyrics: Daft Punk - One More Time
letra: Queen - Don't Stop Me Now
```

---

## 14. Discovery Themed Radios

Injects tracks matching a specific mood or style into your Conveyor buffer:

```text
radio: 90s Grunge and Alternative Rock
radio: Late night Lo-Fi Synthwave for coding
radio: 2000s Spanish Indie Rock
```

---

## 🔄 Feedback Loop and Error Reporting

When the engine processes the mailbox:
1. **Successful orders**: Cleared from the file to keep it clean.
2. **`info:` queries**: Appended at the bottom under `# --- TRACK INFORMATION (Results) ---`.
3. **Failed orders**: Retained under `# --- UNCOMPLETED ORDERS (See details below) ---` with error notes (`# ERROR:` or `# NOTICE:`).

---

<p align="center">
  <a href="cli-reference.md"><b>⬅ CLI Reference</b></a> • <a href="mobile-and-sync.md"><b>Next: Mobile Ecosystem & Sync ➡</b></a>
</p>
