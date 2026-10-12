# 💾 Backups, Snapshots & PC Migration

<p align="center">
  <img src="https://img.shields.io/badge/backup-zero_downtime-brightgreen?style=for-the-badge&logo=sqlite&logoColor=white" alt="Zero Downtime Backup">
  <img src="https://img.shields.io/badge/deduplication-SHA--256-blue?style=for-the-badge" alt="SHA-256 Dedup">
  <img src="https://img.shields.io/badge/migration-one_command-orange?style=for-the-badge" alt="One Command Migration">
</p>

Music Engine features an intelligent, centralized backup and migration engine implemented in [`src/backup_manager.py`](../src/backup_manager.py). It ensures zero-downtime hot snapshots, automated retention rotation, SHA-256 hash deduplication, and seamless transfer of your library state to a new PC with automatic path rebasing.

---

## 📑 Table of Contents

- [Core Principles of the Backup Engine](#-core-principles-of-the-backup-engine)
- [1. Single-File Unified Bundle Architecture](#1-single-file-unified-bundle-architecture)
- [2. Hot SQLite Snapshots (Zero Downtime)](#2-hot-sqlite-snapshots-zero-downtime)
- [3. SHA-256 Hash Deduplication](#3-sha-256-hash-deduplication)
- [4. Automated Retention & Rotation](#4-automated-retention--rotation)
- [5. Creating Manual Backups](#5-creating-manual-backups)
- [6. Exporting Migration Bundles](#6-exporting-migration-bundles)
- [7. Restoring & Cross-Machine Path Rebasing](#7-restoring--cross-machine-path-rebasing)
- [Pre-Restore Safety Snapshot](#-pre-restore-safety-snapshot)

---

## 🛡️ Core Principles of the Backup Engine

1. **Hot WAL Consistency:** Uses SQLite's online backup API (`sqlite3.backup()`). Snapshots are 100% consistent and never suffer from torn pages or write lock timeouts.
2. **Unified Single-File Bundles:** Everything needed to recreate your library's state (database, taste profile, download history, folder fingerprints, metadata manifest) is packed into a **single `.tar.gz` archive**.
3. **No Redundant Backups:** If the database content has not changed since the last snapshot, redundant disk writes are automatically skipped.
4. **Self-Healing Restore:** Moving to a new PC with a different username or music path? The restore engine automatically rewrites internal file paths in the database.

---

## 1. Single-File Unified Bundle Architecture

Each `.tar.gz` backup bundle contains:

```text
music_engine_backup_20261012_143000.tar.gz
├── conveyor_state.sqlite           # Clean hot snapshot of the SQLite database
├── manifest.json                   # Metadata: timestamp, version, SHA-256, paths, tags
└── auxiliary/                      # Critical companion runtime state
    ├── taste_profile.json          # AI curator listening profile
    ├── download_archive.txt        # Historical yt-dlp IDs archive
    └── playlist_folder_state.json  # Playlist fingerprint cache
```

---

## 2. Hot SQLite Snapshots (Zero Downtime)

Traditional file copying (`cp conveyor_state.sqlite ...`) can produce corrupted or locked databases when SQLite is running in WAL (Write-Ahead Logging) mode.

Music Engine uses the internal Python `sqlite3.backup()` API:
- Checkpoints active WAL journals safely.
- Locks pages atomically in memory.
- Writes a pristine, independent copy without interrupting ongoing downloads or playback.

---

## 3. SHA-256 Hash Deduplication

To prevent filling your disk with identical daily backups when no new songs were added or played:
1. Before writing a snapshot, the engine computes a SHA-256 hash of the current database.
2. It compares it against the hash marker in `data/.last_backup_hash`.
3. If the hash matches, the backup is skipped:
   ```text
   [i] State unchanged since last snapshot. Deduplication skipped redundant backup.
   ```
4. You can override deduplication anytime with the `--force` flag.

---

## 4. Automated Retention & Rotation

Configured in `config/config.yaml`:

```yaml
backup:
  auto_backup: true      # Automatically runs on every engine cycle
  dir: "data/backups"    # Destination directory
  max_backups: 10        # Automatic rolling retention limit
  format: "bundle"       # "bundle" (.tar.gz) or "db_only" (.sqlite.gz)
  dedup_by_hash: true    # Enable SHA-256 deduplication
```

When new snapshots exceed `max_backups`, the oldest archives are automatically pruned.

---

## 5. Creating Manual Backups

### Create a Snapshot
```bash
python main.py backup
```

### Tag a Snapshot with a Description
```bash
python main.py backup --tag "before_curation_fill"
```

### Force a Snapshot Bypassing Deduplication
```bash
python main.py backup --force
```

### List Available Snapshots
```bash
python main.py backup --list
```

*Example Output:*
```text
=======================================================
 AVAILABLE SNAPSHOTS (3 in /home/user/Music_Engine/data/backups)
=======================================================
 • music_engine_backup_20261012_143000 [manual]
    Date: 2026-10-12 14:30:00 | Size: 412.5 KB | Format: bundle
 • music_engine_backup_20261011_040000 [auto]
    Date: 2026-10-11 04:00:00 | Size: 410.2 KB | Format: bundle
=======================================================
```

---

## 6. Exporting Migration Bundles

To transfer your entire engine state to a new computer or server:

```bash
# Export to default directory:
python main.py export-backup

# Export to a specific location (e.g. USB flash drive or desktop):
python main.py export-backup -o ~/Desktop/music_engine_migration.tar.gz
```

*Output:*
```text
[✓] Migration bundle exported successfully: /home/user/Desktop/music_engine_migration.tar.gz
    You can copy this file to another machine and run:
    python main.py restore-backup music_engine_migration.tar.gz
```

---

## 7. Restoring & Cross-Machine Path Rebasing

When restoring a backup on another computer, usernames and home directories often differ:
- **Old PC:** `/home/aitor/Music/Songs/...`
- **New PC:** `/home/server/Media/Music/...`

The `restore-backup` command automatically detects path discrepancies and rewrites all stored audio file paths in the database to point to the new location.

### Restoring on the Same PC
```bash
python main.py restore-backup data/backups/music_engine_backup_20261012_143000.tar.gz
```

### Restoring on a New PC with a Different Music Directory
```bash
python main.py restore-backup ~/music_engine_migration.tar.gz --target-base-dir ~/Media/Music
```

*Summary Output:*
```text
=======================================================
 RESTORE SUMMARY
=======================================================
 - Total tracks in database: 1416
 - Rebased path references:  1416
 - Components restored:      database, taste_profile.json, download_archive.txt, playlist_folder_state.json
 - Base directory rebased:   '/home/aitor/Music/Songs' -> '/home/server/Media/Music'
=======================================================
```

---

## 🛡️ Pre-Restore Safety Snapshot

Before modifying any active database file or extracting archives during a restore operation, Music Engine **automatically creates an emergency pre-restore snapshot** of your existing state:

```text
data/backups/pre_restore_safety_backup_YYYYMMDD_HHMMSS.sqlite.gz
```

If a restore operation is accidentally interrupted or pointed at the wrong backup file, your pre-existing data remains 100% safe and recoverable.

---

<p align="center">
  <a href="metadata-and-lyrics.md"><b>⬅ Metadata & Lyrics</b></a> • <a href="troubleshooting.md"><b>Next: Troubleshooting & FAQ ➡</b></a>
</p>
