# TASK-03: ListenBrainz MSID Cache & Loved Tracks Resolver

- **Priority:** P1 (High)
- **Target Files:**
  - `src/telemetry.py`
  - `database/schema.sql`
  - `src/db.py`
- **Estimated Complexity:** Medium
- **Status:** Ready for implementation

---

## 1. Problem Description & Root Cause Analysis

* **The Problem:** In [`src/telemetry.py`](file:///home/usumaniana/Documentos/Proyectos/Music_Engine/src/telemetry.py#L173-L200), `get_loved_tracks()` retrieves loved tracks (`score == 1`) from the ListenBrainz feedback endpoint. These items contain only a `recording_msid` (MessyBrainz identifier), without track or artist names.
* **Current Flawed Implementation:** To resolve what song an MSID refers to, the code executes a loop of up to 10 HTTP requests to `/user/{self.lb_user}/listens` (fetching up to 500 recent scrobbles) on **every single engine run**:
  ```python
  for _ in range(10): # Fetch up to 500 recent listens
      ...
      for lst in ls_data:
          msid = lst.get('recording_msid')
          ...
          if msid and artist and title:
              msid_map[msid] = (artist, title)
  ```
* **Failure Modes:**
  1. **Older Loved Tracks are Permanently Missed:** If a user loved a song on mobile 3 weeks ago and it has slipped past the last 500 scrobbles, it will **never be resolved** and will never be shielded in `Permanent`.
  2. **Wasteful Network & API Quota:** 10 HTTP requests are dispatched on every engine run cycle just to repeatedly resolve the same static MSIDs over and over.

---

## 2. Step-by-Step Implementation Instructions

### Step 1: Add `msid_cache` Table to Database Schema
In `database/schema.sql` and `src/db.py`:
```sql
CREATE TABLE IF NOT EXISTS msid_cache (
    msid TEXT PRIMARY KEY,
    artist TEXT NOT NULL,
    title TEXT NOT NULL,
    resolved_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_msid_cache ON msid_cache(msid);
```

### Step 2: Update `get_loved_tracks()` in `src/telemetry.py`
Refactor `get_loved_tracks()` with persistent caching and ListenBrainz metadata lookup:
1. Retrieve feedback from ListenBrainz:
   `GET {self.api_url}/feedback/user/{self.lb_user}/get-feedback?score=1`
2. Extract all `loved_msids`.
3. Query SQLite `msid_cache` for already resolved MSIDs:
   ```python
   with get_db_connection(self.db_path) as conn:
       cursor = conn.cursor()
       placeholders = ','.join('?' for _ in loved_msids)
       cursor.execute(f"SELECT msid, artist, title FROM msid_cache WHERE msid IN ({placeholders})", loved_msids)
       msid_map = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
   ```
4. Identify missing MSIDs: `unresolved_msids = [m for m in loved_msids if m not in msid_map]`
5. For unresolved MSIDs:
   - Option A: Query ListenBrainz metadata lookup API:
     `GET https://api.listenbrainz.org/1/metadata/lookup/?recording_msids=<msid1>&recording_msids=<msid2>`
   - Option B: If the lookup API is unavailable, fetch recent listens once and cache all observed `(recording_msid -> artist, title)` pairs into `msid_cache` with `INSERT OR REPLACE INTO msid_cache`.
6. Insert newly resolved MSIDs into `msid_cache`.
7. Return `[msid_map[m] for m in loved_msids if m in msid_map]`.

---

## 3. Verification & Acceptance Criteria

1. **Cache Persistence Test:**
   Manually insert an MSID into `msid_cache`. Call `get_loved_tracks()`. Verify the track is resolved directly from SQLite with 0 requests to `/listens`.
2. **Quota Efficiency:**
   When all loved tracks are cached, `get_loved_tracks()` performs only 1 request to `/get-feedback` instead of 11 HTTP requests.
3. **No Dropped Loves:**
   Loved tracks older than the 500-scrobble window are resolved and shielded in `Permanent`.
