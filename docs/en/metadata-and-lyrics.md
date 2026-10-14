# 🎶 Metadata, Genres & Synchronized Lyrics

<p align="right">
  <b>Language / Idioma:</b>
  <b>English</b> | <a href="../es/metadata-and-lyrics.md">Español</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/lyrics-synchronized_.lrc-blue?style=for-the-badge&logo=music&logoColor=white" alt="Synced Lyrics">
  <img src="https://img.shields.io/badge/genres-AI_%2B_MusicBrainz-orange?style=for-the-badge&logo=google&logoColor=white" alt="Genres AI MusicBrainz">
  <img src="https://img.shields.io/badge/metadata-studio_albums-green?style=for-the-badge" alt="Studio Albums">
</p>

Music Engine maintains pristine audiophile standards. Rather than settling for loose singles, incomplete tags, or mismatched versions, the engine includes a robust enrichment pipeline that guarantees official studio metadata, granular genres, and millisecond-accurate synchronized lyrics.

---

## 📑 Table of Contents

- [The Enrichment Pipeline](#-the-enrichment-pipeline)
- [1. Synchronized Lyrics Cascade](#1-synchronized-lyrics-cascade)
  - [Provider Hierarchy](#provider-hierarchy)
  - [Dual Tagging: Embedded Vorbis/MP4 & .lrc Sidecars](#dual-tagging-embedded-vorbismp4--lrc-sidecars)
  - [Scanning & Upgrading Lyrics](#scanning--upgrading-lyrics)
- [2. Intelligent Genre Classification](#2-intelligent-genre-classification)
  - [Multi-Tier Classification Strategy](#multi-tier-classification-strategy)
  - [The `artist_genres` Cache](#the-artist_genres-cache)
  - [Genre CLI Commands](#genre-cli-commands)
- [3. Track Numbers & Release Dates](#3-track-numbers--release-dates)
- [4. Heuristic Studio Album Resolution](#4-heuristic-studio-album-resolution)
  - [Prioritizing Studio Albums over Singles](#prioritizing-studio-albums-over-singles)
  - [Antagonistic Keyword Exclusion Filter](#antagonistic-keyword-exclusion-filter)
- [5. Auditing & Fixing Dubious Tracks (`fix-metadata`)](#5-auditing--fixing-dubious-tracks-fix-metadata)

---

## 🔄 The Enrichment Pipeline

```text
 Audio File Downloaded (.opus / .m4a)
                 │
                 ├──▶ 1. Lyrics Cascade ──────▶ [LRCLIB] ──▶ [syncedlyrics] ──▶ [YTMusic]
                 │                                │
                 │                                ├──▶ Embed Vorbis/MP4 lyric tags
                 │                                └──▶ Generate contiguous <Track>.lrc
                 │
                 ├──▶ 2. Genre Resolver ──────▶ [MusicBrainz] ──▶ [Deezer] ──▶ [Gemini AI]
                 │                                │
                 │                                └──▶ Write genre tag & update SQLite
                 │
                 └──▶ 3. Track Numbers & Dates ──▶ [YTMusic Album Tracklist API]
                                                  │
                                                  └──▶ Write tracknumber, date & SQLite
```

---

## 1. Synchronized Lyrics Cascade

Lyrics are retrieved using a multi-source fallback cascade implemented in [`src/lyrics_provider.py`](../../src/lyrics_provider.py):

### Provider Hierarchy

1. **LRCLIB API (Primary):** Open-source synchronized lyrics database with precise millisecond timestamps (`[mm:ss.xx]`).
2. **`syncedlyrics` (Secondary):** Automated multi-scraper querying NetEase, Musixmatch, Megalobiz, and Deezer.
3. **YouTube Music Lyrics API (Tertiary):** Official lyrics extracted from the YouTube Music `get_watch_playlist` / `get_lyrics` endpoint.
4. **lyrics.ovh (Fallback):** Plain unsynchronized text lyrics when no timestamped source is available.

---

### Dual Tagging: Embedded Vorbis/MP4 & `.lrc` Sidecars

Music Engine writes lyrics in two distinct places for 100% universal compatibility:

1. **Embedded Audio File Tags:**
   - **Opus (Vorbis Comments):** Injected into `LYRICS`, `SYNCEDLYRICS`, and `UNSYNCEDLYRICS` tags using Mutagen.
   - **M4A / AAC (MP4 Atoms):** Injected into `©lyr` atom.
2. **Sidecar `.lrc` Files:**
   - Saved right next to the audio file:
     ```text
     Permanent/Arctic Monkeys/AM/Arctic Monkeys - Do I Wanna Know.opus
     Permanent/Arctic Monkeys/AM/Arctic Monkeys - Do I Wanna Know.lrc
     ```
   - Standard format:
     ```text
     [00:15.20] Have you got colour in your cheeks?
     [00:18.45] Do you ever get that fear that you can't shift the type...
     ```
   - Instantly detected and displayed by **Lune**, **Auxio**, **Symfonium**, **Poweramp**, and desktop players.

---

### Scanning & Upgrading Lyrics

To scan your library and upgrade plain lyrics to synchronized `.lrc` files:

```bash
# Scan a batch of 50 tracks:
python main.py enrich-lyrics

# Scan entire collection without limit:
python main.py enrich-lyrics --all

# Download missing lyrics without attempting to upgrade existing plain text ones:
python main.py enrich-lyrics --no-upgrade
```

---

## 2. Intelligent Genre Classification

Implemented in [`src/genre_resolver.py`](../../src/genre_resolver.py).

### Multi-Tier Classification Strategy

1. **Step 1: Local SQLite Cache (`artist_genres` table)**
   - If the artist's genre has already been classified, it resolves instantaneously (0 ms) without network calls.
2. **Step 2: MusicBrainz API**
   - Queries open MusicBrainz artist tags and genres.
3. **Step 3: Google Gemini AI (Semantic Classification)**
   - When open databases lack genre tags or categorize an artist vaguely (e.g. *"Music"*), Gemini analyzes the artist's discography and assigns accurate, standardized genres (e.g. *"Synthwave"*, *"Indie Rock"*, *"Neo-Soul"*).

### The `artist_genres` Cache

Stored inside `data/conveyor_state.sqlite`:
```sql
CREATE TABLE artist_genres (
    artist TEXT PRIMARY KEY,
    genre TEXT NOT NULL,
    source TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Genre CLI Commands

```bash
# Process batch of 50 pending tracks:
python main.py enrich-genres

# Reclassify all tracks across the entire library:
python main.py enrich-genres --all --force-all

# Run genre classification without AI (MusicBrainz only):
python main.py enrich-genres --all --no-ai
```

---

## 3. Track Numbers & Release Dates

Albums in the Permanent library are enriched with official disc track numbers and original release dates via [`src/enrich_track_meta.py`](../../src/enrich_track_meta.py):

- Fetches canonical track sequencing directly from YouTube Music album manifests.
- Tags audio files with `tracknumber` and `date` / `year`.
- Updates `track_number` and `release_date` fields in the `tracks` database table.

```bash
# Enrich tracks lacking track numbers or dates:
python main.py enrich-metadata

# Force re-analysis across the entire library:
python main.py enrich-metadata --force-all
```

---

## 4. Heuristic Studio Album Resolution

Implemented in [`src/album_resolver.py`](../../src/album_resolver.py).

### Prioritizing Studio Albums over Singles

Loose standalone singles often contain promotional album art, non-standard titling, or lack album context. When discovering or downloading tracks, Music Engine:

1. Identifies if a release is a studio album using `is_studio_album()`.
2. Searches YouTube Music for the artist's official studio album catalog.
3. Awards a **+100 heuristic match bonus** to official studio album tracks over standalone singles.

### Antagonistic Keyword Exclusion Filter

A common issue in automated downloaders is confusing tracks with similar titles on the same album. Music Engine includes a strict **antagonistic keyword filter**:

| Track Query | Rejected Album Version | Reason |
| :--- | :--- | :--- |
| *"Nuestro Primer Baile"* | *"Nuestro Último Baile"* | Antonyms `Primer` vs `Último` (First vs Last) |
| *"Track Title (Original)"* | *"Track Title (Remix)"* | Incompatible type `Original` vs `Remix` |
| *"Song (Intro)"* | *"Song (Outro)"* | Incompatible position `Intro` vs `Outro` |

This prevents false positive matches and ensures you always get the exact track you requested.

---

## 5. Auditing & Fixing Dubious Tracks (`fix-metadata`)

Over time, algorithmic search results can occasionally match bootlegs, 8-bit covers, acoustic tributes, or karaoke uploads.

The `fix-metadata` command audits your library against known problematic patterns (`FORBIDDEN_WORDS`):
- `karaoke`, `cover`, `instrumental cover`, `tribute`, `8-bit`, `slowed + reverb`, `live at...`

```bash
# Audit and auto-repair dubious tracks:
python main.py fix-metadata

# Audit using Gemini AI as a final tiebreaker:
python main.py fix-metadata --use-ai
```

When a repairable track is detected, the engine:
1. Locates the genuine studio album version.
2. Replaces the YouTube video ID in the database.
3. Removes the old corrupted audio file and `.lrc`.
4. Queues the official version for download.

---

<p align="center">
  <a href="automation.md"><b>⬅ Background Automation</b></a> • <a href="backup-and-migration.md"><b>Next: Backups & Migration ➡</b></a>
</p>
