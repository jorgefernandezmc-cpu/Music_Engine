# 📱 Remote Control Mailbox (`requests.txt` / `peticiones.txt`)

<p align="right">
  <b>Language / Idioma:</b>
  <b>🇬🇧 English</b> | <a href="../es/mailbox-commands.md">🇪🇸 Español</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/feature-remote_mailbox-purple?style=for-the-badge&logo=fastapi&logoColor=white" alt="Remote Mailbox">
  <img src="https://img.shields.io/badge/bilingual-English%20&%20Spanish-orange?style=for-the-badge" alt="Bilingual">
</p>

The **Remote Control Mailbox** allows you to issue commands, download albums, queue temporary cravings, promote tracks, or correct metadata directly from your smartphone without opening a terminal or SSH session.

---

## 📑 Table of Contents

- [How the Mailbox Works](#-how-the-mailbox-works)
- [Command Syntax Summary Table](#-command-syntax-summary-table)
- [1. Full Studio Album Downloads](#1-full-studio-album-downloads)
- [2. Individual Track Downloads](#2-individual-track-downloads)
- [3. Temporary Cravings / Antojos Buffer](#3-temporary-cravings--antojos-buffer)
- [4. Promotion & Shielding to Permanent](#4-promotion--shielding-to-permanent)
- [5. Discarding & Purging Tracks](#5-discarding--purging-tracks)
- [6. Metadata & Album Reassignments](#6-metadata--album-reassignments)
- [7. Music Genre Corrections](#7-music-genre-corrections)
- [8. Synchronized Lyrics Fetching](#8-synchronized-lyrics-fetching)
- [9. Thematic Discovery Radios](#9-thematic-discovery-radios)
- [10. Audio Track Self-Repair](#10-audio-track-self-repair)
- [The Feedback Loop & Error Handling](#-the-feedback-loop--error-handling)

---

## 📬 How the Mailbox Works

```text
 ┌────────────────┐          Syncthing          ┌────────────────┐
 │  Mobile Phone  │  ─────────────────────────▶ │ PC Music Engine│
 │  (Text Editor) │  ◀───────────────────────── │  (Background)  │
 └────────────────┘                             └────────────────┘
         │                                              │
         ▼                                              ▼
 Edit requests.txt                          Reads lines on cycle,
 inside synced folder                       downloads audio/lyrics,
                                            clears finished commands,
                                            leaves error comments
```

1. Inside your base music directory (`storage.base_dir`), open the file `requests.txt` (or `peticiones.txt`) using any text editor or note app on your phone.
2. Add your instructions at the bottom of the file (below the commented header `#`).
3. Save the file. **Syncthing** syncs it instantly to your PC.
4. On the next engine run cycle (via `systemd` or manual `main.py run`), the engine parses, executes, and clears successful orders while leaving error feedback if a song cannot be found.

---

## 📋 Command Syntax Summary Table

The mailbox supports both **English** and **Spanish** syntax natively:

| Operation | English Syntax | Spanish Syntax | Destination |
| :--- | :--- | :--- | :--- |
| **Permanent Album** | `album: Artist - Album`<br>`permanent album: Artist - Album` | `disco: Artista - Disco`<br>`permanente album: Artista - Disco` | `Permanent/<Artist>/<Album>/` |
| **Craving Album** | `craving album: Artist - Album` | `antojo album: Artista - Disco` | `Cravings/<Artist>/<Album>/` |
| **Permanent Track** | `permanent: Artist - Track`<br>`Download "Track" by Artist` | `permanente: Artista - Tema`<br>`Descargar "Tema" de Artista` | `Permanent/<Artist>/<Album>/` |
| **Craving Track** | `craving: Artist - Track` | `antojo: Artista - Tema` | `Cravings/<Artist>/<Album>/` |
| **Promote Track** | `permanent: Track`<br>`favorite: Track`<br>`shield: Track` | `permanente: Tema`<br>`favorita: Tema`<br>`blindar: Tema` | Moves to `Permanent/` |
| **Purge Track** | `purge: Track`<br>`delete: Track` | `borrar: Tema`<br>`eliminar: Tema` | Deletes file + `.lrc` + marks `PURGED` |
| **Reassign Album** | `album: Track -> New Album` | `album: Tema -> Nuevo Álbum` | Moves files & tags to new folder |
| **Update Genre** | `genre: Track -> New Genre`<br>`genre: Track` (AI re-analysis) | `genero: Tema -> Nuevo Género`<br>`genero: Tema` | Embeds tag into audio & SQLite |
| **Refresh Lyrics** | `lyrics: Track` | `letra: Tema` | Re-fetches synced `.lrc` sidecar |
| **Thematic Radio** | `radio: Vibe Description` | `radio: Descripción de Estilo` | Fills Conveyor with matching vibe |
| **Repair Track** | `fix: Track`<br>`repair: Track` | `reparar: Tema`<br>`arreglar: Tema` | Replaces with official studio track |

---

## 1. Full Studio Album Downloads

Downloads complete official tracklists directly from YouTube Music.

```text
# Downloads full Dark Side of the Moon album to Permanent:
album: Pink Floyd - The Dark Side of the Moon

# Explicit permanent album syntax:
permanent album: Rosalía - Motomami

# Natural language syntax:
Download the album "Random Access Memories" by Daft Punk
```

The engine:
- Resolves official track numbers and release year.
- Downloads every track directly to `Permanent/<Primary_Artist>/<Album>/`.
- Embeds cover art and metadata.
- Fetches synchronized `.lrc` sidecars for every track.
- Adds tracks to `Permanent.m3u8` and regenerates playlist backups.

---

## 2. Individual Track Downloads

Downloads single tracks directly into the permanent library:

```text
# Structured syntax:
permanent: Daft Punk - Get Lucky
permanent: Kendrick Lamar - Not Like Us

# Natural language:
Download "Starboy" by The Weeknd
Descargar "Ojitos Lindos" de Bad Bunny
```

---

## 3. Temporary Cravings / Antojos Buffer

Got an itch for a summer anthem, a viral single, or a soundtrack you don't necessarily want in your permanent collection forever? Queue it as a **Craving**:

```text
# Single track craving:
craving: Charli xcx - Apple
antojo: Quevedo - Columbia

# Complete album craving:
craving album: Arctic Monkeys - AM
antojo album: C. Tangana - El Madrileño
```

> [!NOTE]
> - Cravings are saved into `storage.cravings_dir` (e.g. `Cravings/` or `Antojos/`).
> - They are automatically included in `Cravings.m3u8` playlist.
> - Tracks in Cravings are automatically purged from disk once they exceed `cravings.retention_days` (default: 30 days) without requiring manual cleanup.
> - If you fall in love with a craving, promote it to permanent at any time using `favorite: Track Name`!

---

## 4. Promotion & Shielding to Permanent

If you discover a gem in your **Conveyor** discovery buffer or in your **Cravings** folder that you want to keep forever:

```text
favorite: Midnight City
permanent: Midnight City
shield: Midnight City
blindar: Midnight City
```

The engine instantly:
1. Locates the audio file and its `.lrc` lyrics.
2. Identifies the canonical studio album for the track.
3. Physically moves the files into `Permanent/<Primary_Artist>/<Album>/`.
4. Updates its database record to `PERMANENT` with `is_permanent = 1`.
5. Removes empty source folders and updates playlists.

---

## 5. Discarding & Purging Tracks

If you don't like a track currently in the Conveyor or Cravings:

```text
purge: Track Name
delete: Track Name
borrar: Track Name
eliminar: Track Name
```

The engine immediately removes the audio file and `.lrc` sidecar from disk, marks the track as `PURGED` in the database, and guarantees the AI curator will **never** suggest or download that track again.

---

## 6. Metadata & Album Reassignments

Sometimes a song was downloaded with an incorrect album name or belongs to a deluxe version. You can reassign it without touching files manually:

```text
# Format: album: <track> -> <target_album>
album: Instant Crush -> Random Access Memories (10th Anniversary)
disco: Bohemian Rhapsody -> A Night at the Opera

# Natural language syntax:
Move the song "Around the World" to album "Homework"
Mueve la canción "Starboy" al álbum "Starboy"
```

The engine re-tags the file, renames directories, moves `.lrc` sidecars, and cleans empty leftover folders.

---

## 7. Music Genre Corrections

If a song was tagged with an overly generic genre (e.g., `Pop`) and you want it tagged with precision:

```text
# Manual assignment:
genre: Midnight City -> Synthwave / Dream Pop
genero: Master of Puppets -> Thrash Metal

# AI re-analysis (omit the target genre):
genre: Midnight City
genero: Bohemian Rhapsody
```

---

## 8. Synchronized Lyrics Fetching

Forces an immediate scan across LRCLIB, syncedlyrics, and YouTube Music for updated synchronized lyrics:

```text
lyrics: Daft Punk - One More Time
letra: Queen - Don't Stop Me Now
```

---

## 9. Thematic Discovery Radios

Injects a batch of fresh discoveries matching a specific mood or theme into your Conveyor buffer:

```text
radio: 90s Grunge and Alternative Rock
radio: Late Night Lo-Fi Synthwave Coding
radio: 2000s Spanish Indie Rock
```

---

## 10. Audio Track Self-Repair

Replaces an inferior live bootleg, remix, or low-quality upload with the official studio release:

```text
fix: Hotel California
repair: Pink Floyd - Comfortably Numb
reparar: Rosalía - Malamente
```

---

## 🔄 The Feedback Loop & Error Handling

When the engine processes `requests.txt`:

1. **Successful orders are automatically removed** from the file to keep it clean.
2. The default guide header is preserved at the top.
3. If an order fails (e.g., track not found on YouTube Music or missing in Conveyor), the command is retained at the bottom with a descriptive `# ERROR:` comment:

```text
# Example of mailbox feedback after an engine run:
# --- UNCOMPLETED ORDERS (See details below) ---
permanent album: Some Unknown Band - Nonexistent Album  # ERROR: Album not found on YouTube Music
```

You can fix typos or delete failed lines anytime.

---

<p align="center">
  <a href="cli-reference.md"><b>⬅ CLI Reference</b></a> • <a href="mobile-and-sync.md"><b>Next: Mobile Ecosystem & Sync ➡</b></a>
</p>
