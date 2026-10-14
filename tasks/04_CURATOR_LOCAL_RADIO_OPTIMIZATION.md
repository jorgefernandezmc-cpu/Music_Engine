# TASK-04: Curator Local Radio Context & Scalability

- **Priority:** P2 (Medium)
- **Target Files:**
  - `src/curator_llm.py`
- **Estimated Complexity:** Medium
- **Status:** Ready for implementation

---

## 1. Problem Description & Root Cause Analysis

* **The Problem:** In [`src/curator_llm.py`](file:///home/usumaniana/Documentos/Proyectos/Music_Engine/src/curator_llm.py#L438-L465), `generate_local_radio(vibra)` queries all tracks currently on the device:
  ```python
  cursor.execute("SELECT id, artist, title, file_path FROM tracks WHERE status IN ('CINTA', 'PERMANENT')")
  all_tracks = cursor.fetchall()
  ```
  It then appends **every single track in the library** to the prompt sent to Gemini:
  ```python
  for t_id, t_artist, t_title, _ in all_tracks:
      prompt += f"[{t_id}] {t_artist} - {t_title}\n"
  ```
* **Failure Modes:**
  1. **Token Exhaustion & Latency:** In a library with 3,000 to 10,000 songs, this produces a prompt of 60,000+ tokens, causing high API costs, slow response times, or token limit exceptions.
  2. **Blind Model Decisions:** The prompt omits the `genre` column! The AI is expected to identify songs matching a vibe (e.g. `"techno melódico"`, `"reggaeton fiesta"`, `"rock clásico 80s"`) relying solely on track title and artist name without knowing the actual genre tags stored in the database.

---

## 2. Step-by-Step Implementation Instructions

### Step 1: Pre-Filter Candidates by Genre & Keyword Affinity
In `generate_local_radio(vibra: str)`:
1. Query tracks including the `genre` column:
   ```python
   cursor.execute("""
       SELECT id, artist, title, genre, file_path 
       FROM tracks 
       WHERE status IN ('CINTA', 'PERMANENT') AND file_path IS NOT NULL
   """)
   all_tracks = cursor.fetchall()
   ```
2. If total tracks $\le 120$, pass all tracks directly.
3. If total tracks $> 120$, implement an intelligent pre-selection:
   - Tokenize `vibra` into search tokens (e.g. `"reggaeton"`, `"techno"`, `"rock"`, `"chill"`, `"entrenar"`).
   - Score each track:
     - $+5$ points if vibe token matches `genre` (case-insensitive substring or fuzzy match).
     - $+3$ points if vibe token matches `title` or `artist`.
     - $+1$ point bonus for higher `play_count` (familiar favorites).
   - Select the top 100 highest-affinity candidates + 30 randomly sampled tracks for discovery (total 130 candidates max).

### Step 2: Enrich Prompt Representation
Include genre context for each candidate track in the prompt:
```python
prompt += f"[{t_id}] {t_artist} - {t_title} [Genre: {t_genre or 'Varied'}]\n"
```

### Step 3: Enforce Valid M3U8 Formatting
Ensure the generated `Radio_<Vibe>.m3u8` playlist includes exact duration and standard `#EXTINF` directives:
```python
with open(m3u8_path, 'w', encoding='utf-8') as f:
    f.write("#EXTM3U\n")
    for t_id in selected_ids:
        track_info = track_map.get(t_id)
        if track_info and os.path.exists(track_info['file_path']):
            dur = track_info['duration_seconds'] or -1
            title_display = f"{track_info['artist']} - {track_info['title']}"
            rel_path = os.path.relpath(track_info['file_path'], self.paths.playlists_dir)
            f.write(f"#EXTINF:{dur},{title_display}\n")
            f.write(f"{rel_path}\n")
```

---

## 3. Verification & Acceptance Criteria

1. **Large Library Simulation Test:**
   With a test database containing 2,000 dummy tracks, verify that `generate_local_radio` sends at most 130 candidates to Gemini instead of 2,000.
2. **Context Fidelity:**
   Verify that tracks containing matching genres are prioritized in the candidate list.
3. **M3U8 Integrity:**
   Verify that the resulting `.m3u8` playlist contains `#EXTINF` duration headers and valid relative paths readable by players like VLC, Symfonium, and Lune.
