# TASK-05: System Health Audit (`doctor` command) & Syncthing Cleaner

- **Priority:** P2 (Medium)
- **Target Files:**
  - `src/cli.py`
  - `src/sync.py`
  - `src/engine.py`
- **Estimated Complexity:** Medium
- **Status:** Ready for implementation

---

## 1. Problem Description & Root Cause Analysis

### 1. Syncthing Conflict Files
* **The Problem:** When bidirectional sync runs between PC and Android, concurrent metadata edits or tag changes often cause Syncthing to write conflict files:
  `Artist - Title.sync-conflict-20261014-123456-ABC.opus`
* **Impact:** These files accumulate in `Permanent` and `Conveyor`, waste storage, confuse `clean_ghost_tracks()`, and can lead to duplicate playlist entries.

### 2. Lack of Centralized Health Diagnostics (`doctor`)
* **The Problem:** When something fails (e.g. invalid Gemini key, expired ListenBrainz token, broken SQLite WAL lock, insufficient disk space, or corrupt audio tags), users must inspect multiple log files (`logs/engine.log`, `logs/downloader.log`, `logs/telemetry.log`).
* **Objective:** Implement a single `main.py doctor` CLI command that performs a non-destructive audit of all subsystems and outputs a clean, colored status report.

---

## 2. Step-by-Step Implementation Instructions

### Step 1: Syncthing Conflict Cleaner in `src/sync.py`
Add method `clean_syncthing_conflicts()` to `FileSyncManager`:
```python
def clean_syncthing_conflicts(self) -> int:
    """
    Detects and safely resolves Syncthing conflict files (*.sync-conflict-*).
    Preserves the file with the newest modification time or largest size,
    and removes redundant conflict sidecars.
    """
    cleaned = 0
    pattern = re.compile(r'^(.*?)\.sync-conflict-\d+-[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)$')
    for dirpath, _, filenames in os.walk(self.paths.base_dir):
        for f in filenames:
            m = pattern.match(f)
            if not m:
                continue
            conflict_path = os.path.join(dirpath, f)
            original_name = m.group(1) + m.group(2)
            original_path = os.path.join(dirpath, original_name)
            
            try:
                if os.path.exists(original_path):
                    # If conflict file is newer and larger, replace original
                    c_stat = os.stat(conflict_path)
                    o_stat = os.stat(original_path)
                    if c_stat.st_mtime > o_stat.st_mtime and c_stat.st_size >= o_stat.st_size:
                        os.replace(conflict_path, original_path)
                    else:
                        os.remove(conflict_path)
                else:
                    # Rename conflict file to original name
                    os.rename(conflict_path, original_path)
                cleaned += 1
                logger.info(f"Resolved Syncthing conflict: {conflict_path}")
            except Exception as e:
                logger.warning(f"Error resolving conflict {conflict_path}: {e}")
    return cleaned
```
Integrate `self.file_sync.clean_syncthing_conflicts()` into `MusicEngine._run_internal()`.

---

### Step 2: Implement `main.py doctor` in `src/cli.py`
Add `subparsers.add_parser("doctor", help="Runs comprehensive health and diagnostic audit")`:

Diagnostics to execute:
1. **Database Integrity:**
   - Run `PRAGMA integrity_check;`
   - Check WAL file size and table row counts.
2. **Filesystem & Disk Space:**
   - Verify `base_dir`, `conveyor_dir`, `permanent_dir`, `cravings_dir`, `playlists_dir` exist and are writable.
   - Check available free disk space on storage mount. Warn if $< 5$ GB.
3. **API Connectivity Checks:**
   - **Gemini:** Verify `GEMINI_API_KEY` exists, is not default placeholder, and perform lightweight ping test.
   - **ListenBrainz:** Verify `LISTENBRAINZ_USER` and `LISTENBRAINZ_TOKEN`, perform `GET /1/validate-token`.
   - **LRCLIB:** Perform ping `GET https://lrclib.net/api/search?q=test` (timeout 3s).
   - **YouTube Music API:** Test `YTMusic().search("test", filter="songs", limit=1)`.
4. **Library Audit:**
   - Count missing physical audio files (`file_path` set in DB but not on disk).
   - Count audio files on disk not indexed in DB.
   - Count tracks with synced `.lrc` vs. unsynced vs. missing.
   - Count unresolved tracks (missing `track_number` or `release_date`).
   - Count Syncthing conflict files.

Format output with standard indicators:
```
===================================================
 MUSIC ENGINE SYSTEM HEALTH AUDIT (DOCTOR)
===================================================
[✓] SQLite Database: Ok (Integrity check passed, 1,420 tracks)
[✓] Storage Paths: Ok (54.2 GB free on /home)
[✓] LRCLIB API: Accessible (latency: 180ms)
[✓] YouTube Music: Operational
[✓] ListenBrainz: Authenticated (User: @example)
[!] Google Gemini: API key configured (gemini-2.5-flash)
[-] Syncthing: 2 conflict files found (run engine to resolve)
[-] Lyrics Coverage: 85% synced, 10% plain, 5% missing
===================================================
```

---

## 3. Verification & Acceptance Criteria

1. Execute `python main.py doctor` on a system with valid configuration and assert output exits with code 0 and displays status for every component.
2. Create a dummy `test.sync-conflict-20261014-123456-ABC.opus` file. Run the cleaner and verify the file is resolved.
