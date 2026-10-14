# TASK-01: Fix Critical Bugs in Downloader & Sync Manager

- **Priority:** P0 (Highest / Immediate)
- **Target Files:**
  - `src/downloader.py`
  - `src/sync.py`
- **Estimated Complexity:** Low
- **Status:** ✅ Completed (Verified)

---

## 1. Problem Description & Root Cause Analysis

### Bug A: `AttributeError: 'Downloader' object has no attribute 'paths'` in `src/downloader.py`
* **File:** `src/downloader.py` (around line 119)
* **Code snippet:**
  ```python
  elif hasattr(self.paths, 'cravings_dir') and self.paths.cravings_dir and (self.paths.cravings_dir in f_path):
      new_status = 'ANTOJO'
  ```
* **Root Cause:**
  In `Downloader.__init__`, `self.paths` is never assigned, and `from src.paths import StoragePaths` is never imported. In Python, evaluating `hasattr(self.paths, ...)` evaluates `self.paths` first as an attribute lookup on `self`. Because `paths` does not exist on `Downloader`, it raises:
  ```
  AttributeError: 'Downloader' object has no attribute 'paths'
  ```
* **Impact:**
  Whenever a track is downloaded that is not permanent (`is_perm == False` or `0`), the download process crashes or fails to classify the downloaded track into `CINTA` or `ANTOJO`.

---

### Bug B: Missing `.lrc` Move & Primary Artist Inconsistency in `src/sync.py`
* **File:** `src/sync.py` (inside `process_local_file_ratings()`, lines 255–265)
* **Code snippet:**
  ```python
  elif rating in (4, 5):
      new_path = self.paths.get_permanente_track_path(t_artist, t_album, t_title)
      if filepath != new_path:
          os.makedirs(os.path.dirname(new_path), exist_ok=True)
          if 'RATING' in audio: 
              del audio['RATING']
          audio.save()
          shutil.move(filepath, new_path)
          cursor.execute("UPDATE tracks SET status = 'PERMANENT', is_permanent = 1, file_path = ? WHERE id = ?", (new_path, t_id))
  ```
* **Root Causes:**
  1. **`.lrc` sidecar is orphaned:** When `shutil.move(filepath, new_path)` moves the audio file, the accompanying `.lrc` file (e.g. `filepath.rsplit('.', 1)[0] + '.lrc'`) is **not moved**. On the next engine run, `clean_ghost_tracks()` detects the `.lrc` without audio and deletes it, destroying verified synced lyrics.
  2. **Violates strict primary artist directory rule:** The destination path is generated using `t_artist` directly. If the artist tag is `"Anther, Dib"` or `"3AM feat. Khea"`, it creates `Permanent/Anther, Dib/...` instead of `Permanent/Anther/...`. The canonical rule requires `get_primary_artist(t_artist)`.
  3. **Empty source directory left behind:** When moving out of `Conveyor` or `Cravings`, the old folder may be left empty.
  4. **Inefficient SQLite Connection Churn:** Inside the `for dirpath, _, filenames in os.walk(self.paths.base_dir):` loop, a new SQLite connection (`with get_db_connection(self.db_path) as conn:`) is created and closed for every single rated file encountered.

---

## 2. Step-by-Step Implementation Instructions

### Step 1: Update `src/downloader.py`
1. Import `StoragePaths` at top of `src/downloader.py`:
   ```python
   from src.paths import StoragePaths
   ```
2. In `Downloader.__init__(self, db_path: str, config_path: str = "config/config.yaml")`:
   ```python
   self.paths = StoragePaths(config_path)
   ```
3. In `download_pending_tracks()`:
   Ensure the condition safely verifies:
   ```python
   if is_perm:
       new_status = 'PERMANENT'
   elif self.paths.cravings_dir and (self.paths.cravings_dir in f_path):
       new_status = 'ANTOJO'
   else:
       new_status = 'CINTA'
   ```

### Step 2: Update `src/sync.py`
1. Ensure `get_primary_artist` is imported in `src/sync.py`:
   ```python
   from src.album_resolver import get_primary_artist
   ```
2. Refactor `process_local_file_ratings()`:
   - Use a single database connection for the operation or batch updates.
   - For `rating in (4, 5)`:
     ```python
     primary_art = get_primary_artist(t_artist)
     clean_alb = t_album if t_album else "Singles"
     ext = os.path.splitext(filepath)[1]
     new_path = self.paths.get_permanente_track_path(primary_art, clean_alb, t_title, ext=ext)
     if filepath != new_path:
         os.makedirs(os.path.dirname(new_path), exist_ok=True)
         if 'RATING' in audio:
             del audio['RATING']
         audio.save()
         shutil.move(filepath, new_path)
         
         # Move companion .lrc sidecar file if present
         old_lrc = os.path.splitext(filepath)[0] + ".lrc"
         new_lrc = os.path.splitext(new_path)[0] + ".lrc"
         if os.path.exists(old_lrc):
             shutil.move(old_lrc, new_lrc)

         # Clean up old empty directory if needed
         old_dir = os.path.dirname(filepath)
         try:
             if os.path.exists(old_dir) and not os.listdir(old_dir):
                 os.rmdir(old_dir)
                 parent_old = os.path.dirname(old_dir)
                 if parent_old and os.path.exists(parent_old) and not os.listdir(parent_old) and parent_old != self.paths.cravings_dir:
                     os.rmdir(parent_old)
         except Exception:
             pass

         cursor.execute("UPDATE tracks SET status = 'PERMANENT', is_permanent = 1, file_path = ? WHERE id = ?", (new_path, t_id))
         conn.commit()
         logger.info(f"Rating {rating}: Moved to Permanent -> {new_path}")
     ```

---

## 3. Verification & Acceptance Criteria

1. **Downloader Initialization Test:**
   Instantiate `dl = Downloader("data/conveyor_state.sqlite")`. Assert `hasattr(dl, 'paths')` is `True` and `dl.paths.cravings_dir` is a valid string path.
2. **Download Status Classification Test:**
   Simulate download of a craving track and verify its status is set to `'ANTOJO'` without raising `AttributeError`.
3. **Rating Move Test:**
   Create a test audio file with `.lrc` in `Cravings/` with Vorbis rating 5. Run `process_local_file_ratings()`.
   Verify:
   - Audio file is moved to `Permanent/<PrimaryArtist>/<Album>/...`.
   - The `.lrc` file is moved alongside the audio file.
   - The original folder is cleaned up if empty.
   - Database record is updated with `is_permanent = 1` and `status = 'PERMANENT'`.
