# TASK-07: Dynamic Affinity Scoring for Conveyor Lifecycle

- **Priority:** P3 (Enhancement / High Value)
- **Target Files:**
  - `src/engine.py`
  - `database/schema.sql`
  - `src/db.py`
  - `config/config.yaml.template`
- **Estimated Complexity:** Medium
- **Status:** Ready for implementation

---

## 1. Problem Description & Root Cause Analysis

* **The Problem:** The Conveyor belt rotation currently relies on static, rigid binary thresholds:
  - Fixed promotion: `play_count >= 15`
  - Fixed purge: `days_unplayed > 150` OR `skip_count >= 5` OR `skip_ratio >= 0.7`
* **Shortcomings:**
  1. **Premature Purging of New Discoveries:** If a user downloads 20 new tracks and happens to skip one twice during the first week while on shuffle, it can rapidly get purged before the user has a genuine chance to appreciate it.
  2. **Binary Cliff:** A track with 14 plays and 0 skips is treated identical to a track with 0 plays that has been idle for 149 days.
  3. **Lack of Velocity & Recency Awareness:** 10 plays in the past 3 days represents high current enthusiasm, whereas 10 plays spread across 4 months represents casual rotation.

---

## 2. Step-by-Step Implementation Instructions

### Step 1: Add `affinity_score` Column to Database
In `database/schema.sql` and `src/db.py`:
```sql
ALTER TABLE tracks ADD COLUMN affinity_score REAL DEFAULT 50.0;
CREATE INDEX IF NOT EXISTS idx_tracks_affinity ON tracks(affinity_score);
```

### Step 2: Implement Dynamic Scoring Engine in `src/engine.py`
Introduce an affinity score formula ($0.0 \dots 100.0$):
$$\text{Score} = \text{Base} + \text{PlayBonus} + \text{VelocityBonus} - \text{SkipPenalty} + \text{ImmunityBoost}$$

```python
def compute_affinity_score(track: dict, recent_listens_count: int, days_since_added: float, days_since_last_play: float) -> float:
    """
    Computes real-time affinity score (0.0 - 100.0) for conveyor tracks.
    """
    play_count = track.get('play_count', 0)
    skip_count = track.get('skip_count', 0)

    # 1. Base Score
    score = 50.0

    # 2. Completed Plays Bonus (up to +40)
    score += min(play_count * 4.0, 40.0)

    # 3. Recent Velocity Bonus (listens within last 14 days)
    score += min(recent_listens_count * 5.0, 20.0)

    # 4. Skip Penalty (attenuated if play_count is already high)
    skip_mitigation = max(0.2, 1.0 - (play_count * 0.05))
    score -= (skip_count * 8.0 * skip_mitigation)

    # 5. Decay penalty for idle tracks without listens
    if days_since_last_play > 45:
        decay_days = days_since_last_play - 45
        score -= min(decay_days * 0.4, 35.0)

    # 6. Discovery Immunity Shield for new tracks (first 14 days)
    if days_since_added <= 14:
        score = max(score, 45.0)

    return max(0.0, min(100.0, round(score, 1)))
```

### Step 3: Refactor Promotion and Purging Logic
In `src/engine.py` (`_run_internal`):
1. **Dynamic Promotion:**
   Promote to `PERMANENT` if:
   - `affinity_score >= 85.0` OR `play_count >= promotion_play_count` (15).
2. **Intelligent Purge:**
   Purge from `CINTA` if telemetry is fresh AND:
   - `days_since_added > 14` AND (`affinity_score <= 15.0` OR `days_since_last_play > grace_period_days`).
3. Update `tracks SET affinity_score = ? WHERE id = ?` during each engine cycle.

---

## 3. Verification & Acceptance Criteria

1. **Immunity Test:**
   A track added 3 days ago with 2 skips and 0 plays must not be purged because its discovery immunity shield keeps score $\ge 45.0$.
2. **Velocity Test:**
   A track with 8 plays in the past week achieves score $> 85.0$ and gets promoted to Permanent ahead of the rigid 15-play threshold.
3. **Graceful Fallback:**
   If `conveyor.smart_scoring: false` is configured in `config.yaml`, the engine seamlessly falls back to legacy binary count rules.
