# TASK-02: Implement Automated Test Suite (PyTest)

- **Priority:** P1 (High)
- **Target Files:**
  - `pytest.ini`
  - `tests/conftest.py`
  - `tests/test_paths.py`
  - `tests/test_album_resolver.py`
  - `tests/test_sync.py`
  - `tests/test_order_processor.py`
  - `tests/test_backup_manager.py`
  - `tests/test_downloader.py`
- **Estimated Complexity:** Medium
- **Status:** Ready for implementation

---

## 1. Problem Description & Root Cause Analysis

* **The Problem:** The repository currently has zero test files (`find . -name "*test*"` returns nothing). Although `pytest>=8.2.2` and `pytest-mock>=3.14.0` are present in `requirements.txt`, there is no regression protection.
* **Impact:** Any modification to path resolution, database schema, fuzzy matching, or file lifecycle operations risks silently breaking core functionality.
* **Objective:** Establish a fast, isolated, automated test harness that runs in under 15 seconds without requiring live network access or real YouTube Music / ListenBrainz API credentials.

---

## 2. Test Architecture & Fixtures Design

### `pytest.ini`
Create `pytest.ini` in the repository root:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
filterwarnings =
    ignore::DeprecationWarning
```

### `tests/conftest.py`
Provide reusable fixtures using `pytest`:
1. `temp_env`: A `tmp_path` fixture configuring a sandbox music base directory (`Conveyor/`, `Permanent/`, `Cravings/`, `Playlists/`, `requests.txt`).
2. `temp_config`: A temporary `config.yaml` pointing to the temporary directories and dummy API settings.
3. `temp_db`: Initializes `database/schema.sql` on a SQLite file inside `tmp_path` and returns its path.
4. `mock_audio_file`: Helper to generate a dummy `.opus` or `.m4a` file with basic Mutagen tags.

---

## 3. Targeted Test Modules

### 3.1. `tests/test_paths.py`
* **Test cases:**
  - `test_sanitize_filename`: Verifies removal of illegal filesystem characters (`/ \ : * ? " < > |`) and trailing dots/spaces.
  - `test_storage_paths_resolution`: Tests path resolution for `conveyor_dir`, `permanent_dir`, `cravings_dir`, `playlists_dir`.
  - `test_primary_artist_path`: Asserts `get_permanente_track_path("Artist A", "Album B", "Song C")` produces `Permanent/Artist A/Album B/Artist A - Song C.opus`.
  - `test_mailbox_header_sync_bilingual`: Tests that changing `system.language` between `"en"` and `"es"` swaps the header in `requests.txt` without deleting pending user commands.

### 3.2. `tests/test_album_resolver.py`
* **Test cases:**
  - `test_get_primary_artist`: Test inputs like `'Anther, Dib' -> 'Anther'`, `'3AM feat. Khea' -> '3AM'`, `'Bad Bunny & Chencho Corleone' -> 'Bad Bunny'`.
  - `test_is_studio_album`: Test detection of singles (`"Song - Single"`, `"- EP"`, same title as album) vs. real studio albums.
  - `test_is_suspicious_match`: Test detection of forbidden keywords (`"cover"`, `"karaoke"`, `"8-bit"`, `"live"`) and mismatching primary artists.
  - `test_antagonistic_keywords`: Ensure distinct keywords like `primer`/`ultimo`, `intro`/`outro` prevent false-positive matching.

### 3.3. `tests/test_sync.py`
* **Test cases:**
  - `test_ghost_cleaner`: Insert 3 tracks into SQLite. Delete physical audio of 1 track. Run `clean_ghost_tracks()`. Verify status is set to `'PURGED'` and companion `.lrc` is removed.
  - `test_mass_deletion_failsafe`: Simulate deletion exceeding `mass_deletion_failsafe_limit` (50). Verify ghost cleaner aborts and does not purge records.
  - `test_sync_manual_moves`: Move a file manually from `Permanent/AlbumA` to `Permanent/AlbumB`. Run `sync_manual_moves()` and verify SQLite record updates.
  - `test_local_file_ratings_promotion`: Create a file in `Cravings` with Vorbis `RATING=5` and companion `.lrc`. Run `process_local_file_ratings()`. Verify both audio and `.lrc` are moved to `Permanent/<PrimaryArtist>/<Album>/`.

### 3.4. `tests/test_order_processor.py`
* **Test cases:**
  - `test_parse_album_move`: Test `album: Track -> NewAlbum` regex and logic.
  - `test_parse_direct_urls`: Test URL extraction for YouTube videos, playlists, and Spotify links.
  - `test_clean_peticiones_file`: Verify only successful orders are removed while comments and errors are retained.

### 3.5. `tests/test_backup_manager.py`
* **Test cases:**
  - `test_create_snapshot_bundle`: Verify `.tar.gz` bundle contains `conveyor_state.sqlite`, `manifest.json`, and auxiliary files.
  - `test_hash_deduplication`: Verify second call to `create_snapshot()` without database changes is skipped unless `force=True`.
  - `test_restore_rebase`: Restore backup snapshot into a simulated target directory with a different username/path and verify paths are rewritten.

---

## 4. Verification & Acceptance Criteria

1. Running `pytest` from the root directory executes all tests and passes 100%:
   ```bash
   pytest
   ```
2. Total execution time of the test suite is under 15 seconds.
3. No tests make real outbound network calls or touch production music directories in `~/Music`.
