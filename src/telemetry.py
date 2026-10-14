import os
import logging
import sqlite3
import time
import re
import unicodedata
import requests
from datetime import datetime, timezone
from thefuzz import fuzz
import yaml
from dotenv import load_dotenv
from src.db import get_db_connection, ensure_db_indexes

# Ensure logs dir exists
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    filename='logs/telemetry.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger('telemetry')

class TelemetryEngine:
    def __init__(self, db_path: str, config_path: str = "config/config.yaml"):
        self.db_path = db_path
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
            
        env_path = os.path.join(os.path.dirname(config_path), '.env')
        load_dotenv(env_path)
            
        self.lb_user = os.getenv('LISTENBRAINZ_USER')
        self.lb_token = os.getenv('LISTENBRAINZ_TOKEN')
        raw_lb_url = self.config.get('telemetry', {}).get('listenbrainz_url', 'https://api.listenbrainz.org/1').rstrip('/')
        if re.search(r'/\d+$', raw_lb_url):
            self.api_url = raw_lb_url
            self.base_url = re.sub(r'/\d+$', '', raw_lb_url)
        else:
            self.base_url = raw_lb_url
            self.api_url = f"{raw_lb_url}/1"
        self.fuzzy_threshold = int(self.config.get('telemetry', {}).get('fuzzy_threshold', 80))
        try:
            with get_db_connection(self.db_path) as conn:
                ensure_db_indexes(conn)
        except Exception as e:
            logger.warning(f"Failed to ensure database indexes in TelemetryEngine: {e}")
        
    def normalize_track_string(self, text: str) -> str:
        """Normalizes track strings removing accents, boilerplate tags, and punctuation."""
        if not text:
            return ""
        # Lowercase
        text = text.lower()
        # Remove accents
        text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
        
        # Regex patterns to remove
        patterns_to_remove = [
            r'\(official.*?\)', r'\[official.*?\]',
            r'\(music video\)', r'\[hq\]',
            r'\(lyric.*?\)', r'\[audio\]', r'\(audio\)',
            r'[\[\(].*?remaster.*?[\]\)]',
            r'[\[\(].*?live.*?[\]\)]',
            r'[\[\(].*?radio edit.*?[\]\)]',
            r'- remaster(ed)?.*',
            r'- radio edit.*',
            r'- live.*',
            r'\(feat\..*?\)', r'ft\..*'
        ]
        
        for pattern in patterns_to_remove:
            text = re.sub(pattern, '', text)
            
        # Remove punctuation and redundant spaces
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text

    def get_last_sync_ts(self) -> int:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM system_metadata WHERE key = 'last_listenbrainz_sync'")
            row = cursor.fetchone()
            if row and row[0]:
                return int(row[0])
        return 0

    def set_last_sync_ts(self, ts: int):
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO system_metadata (key, value) VALUES ('last_listenbrainz_sync', ?)", (str(ts),))
            conn.commit()

    def fetch_listens(self, min_ts: int) -> list:
        if not self.lb_user:
            logger.error("LISTENBRAINZ_USER is not configured.")
            return []
            
        headers = {}
        if self.lb_token:
            headers['Authorization'] = f"Token {self.lb_token}"
            
        url = f"{self.api_url}/user/{self.lb_user}/listens"
        
        all_listens = []
        max_ts_param = None
        pages_fetched = 0
        
        while pages_fetched < 15:
            pages_fetched += 1
            params = {"count": 100}
            if max_ts_param:
                params["max_ts"] = max_ts_param
                
            page_listens = []
            max_retries = 3
            retry_delay = 2
            
            for attempt in range(max_retries):
                try:
                    response = requests.get(url, headers=headers, params=params, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        payload = data.get('payload', {})
                        page_listens = payload.get('listens', [])
                        break
                    elif response.status_code == 429:
                        logger.warning("Request rate-limit reached. Retrying...")
                        time.sleep(retry_delay * (2 ** attempt))
                    else:
                        logger.error(f"HTTP Error {response.status_code}: {response.text}")
                        break
                except requests.RequestException as e:
                    logger.error(f"Network error: {e}")
                    time.sleep(retry_delay * (2 ** attempt))
                    
            if not page_listens:
                break
                
            valid_listens = [l for l in page_listens if l.get('listened_at') > min_ts]
            all_listens.extend(valid_listens)
            
            if len(valid_listens) < len(page_listens):
                break
                
            if not valid_listens:
                break
                
            max_ts_param = valid_listens[-1].get('listened_at') - 1
            time.sleep(0.5) # Respect ListenBrainz rate limit
            
        return all_listens

    def get_loved_tracks(self) -> list[tuple[str, str]]:
        if not self.lb_user:
            logger.error("LISTENBRAINZ_USER is not configured.")
            return []

        url = f"{self.api_url}/feedback/user/{self.lb_user}/get-feedback"
        params = {"score": 1, "count": 100}
        headers = {}
        if self.lb_token:
            headers['Authorization'] = f"Token {self.lb_token}"

        try:
            r = requests.get(url, headers=headers, params=params, timeout=10)
            if r.status_code != 200:
                logger.error(f"Error fetching feedback from ListenBrainz: {r.status_code} - {r.text}")
                return []

            data = r.json() or {}
            feedbacks = data.get('feedback') or []

            loved_msids = []
            newly_resolved = {}

            for item in feedbacks:
                if not item:
                    continue
                if item.get('score') == 1:
                    msid = item.get('recording_msid')
                    if msid:
                        loved_msids.append(msid)
                    # Check if feedback directly supplied track metadata
                    meta = item.get('track_metadata') or {}
                    art = meta.get('artist_name')
                    tit = meta.get('track_name')
                    if msid and art and tit:
                        newly_resolved[msid] = (art, tit)

            if not loved_msids:
                return []

            # Step 1: Query SQLite msid_cache for already resolved MSIDs
            msid_map = {}
            with get_db_connection(self.db_path) as conn:
                ensure_db_indexes(conn)
                cursor = conn.cursor()
                chunk_size = 500
                for i in range(0, len(loved_msids), chunk_size):
                    chunk = loved_msids[i:i + chunk_size]
                    placeholders = ','.join('?' for _ in chunk)
                    cursor.execute(
                        f"SELECT msid, artist, title FROM msid_cache WHERE msid IN ({placeholders})",
                        chunk
                    )
                    for row in cursor.fetchall():
                        msid_map[row[0]] = (row[1], row[2])

            msid_map.update(newly_resolved)
            unresolved_msids = [m for m in loved_msids if m not in msid_map]

            # Step 2: Resolve missing MSIDs if any
            if unresolved_msids:
                logger.info(f"Resolving {len(unresolved_msids)} uncached loved MSIDs...")

                # Option A: ListenBrainz metadata lookup API
                try:
                    lookup_url = f"{self.api_url}/metadata/lookup/"
                    lookup_headers = {}
                    if self.lb_token:
                        lookup_headers['Authorization'] = f"Token {self.lb_token}"
                    for i in range(0, len(unresolved_msids), 50):
                        chunk = unresolved_msids[i:i + 50]
                        r_lookup = requests.get(lookup_url, headers=lookup_headers, params={'recording_msids': chunk}, timeout=10)
                        if r_lookup.status_code == 200:
                            l_data = r_lookup.json() or {}
                            results = l_data.get('results') or l_data.get('payload', {}).get('results') or []
                            for res in results:
                                res_msid = res.get('recording_msid')
                                meta = res.get('track_metadata') or res
                                art = meta.get('artist_name')
                                tit = meta.get('track_name') or meta.get('recording_name')
                                if res_msid and art and tit:
                                    newly_resolved[res_msid] = (art, tit)
                except Exception as e:
                    logger.debug(f"Metadata lookup API unavailable or failed: {e}")

                remaining_unresolved = set(m for m in unresolved_msids if m not in newly_resolved)

                # Option B: Fallback to fetching recent scrobbles to resolve missing MSIDs
                if remaining_unresolved:
                    url_ls = f"{self.api_url}/user/{self.lb_user}/listens"
                    headers_ls = {}
                    if self.lb_token:
                        headers_ls['Authorization'] = f"Token {self.lb_token}"
                    max_ts = None
                    for _ in range(10): # Fetch up to 1000 scrobbles
                        p = {"count": 100}
                        if max_ts:
                            p["max_ts"] = max_ts
                        r_ls = requests.get(url_ls, headers=headers_ls, params=p, timeout=10)
                        if r_ls.status_code != 200:
                            break
                        ls_data = r_ls.json().get('payload', {}).get('listens', [])
                        if not ls_data:
                            break

                        for lst in ls_data:
                            msid = lst.get('recording_msid')
                            meta = lst.get('track_metadata', {})
                            artist = meta.get('artist_name')
                            title = meta.get('track_name')
                            if msid and artist and title:
                                newly_resolved[msid] = (artist, title)
                                remaining_unresolved.discard(msid)

                        if not remaining_unresolved:
                            break

                        max_ts = ls_data[-1].get('listened_at') - 1
                        time.sleep(0.3)

            # Step 3: Insert newly resolved MSIDs into msid_cache
            if newly_resolved:
                with get_db_connection(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.executemany(
                        "INSERT OR REPLACE INTO msid_cache (msid, artist, title) VALUES (?, ?, ?)",
                        [(m, art, tit) for m, (art, tit) in newly_resolved.items()]
                    )
                    conn.commit()
                msid_map.update(newly_resolved)

            # Step 4: Return resolved loved tracks
            seen = set()
            loved = []
            for msid in loved_msids:
                if msid in msid_map:
                    pair = msid_map[msid]
                    if pair not in seen:
                        seen.add(pair)
                        loved.append(pair)

            return loved

        except Exception as e:
            logger.error(f"Error fetching loved tracks: {e}")
            return []


    def process_listens(self) -> tuple[int, list]:
        """
        Downloads new scrobbles, matches against database, and updates play_counts.
        Returns (processed_count, orphan_list).
        """
        min_ts = self.get_last_sync_ts()
        if min_ts == 0:
            lookback_days = int(self.config.get('telemetry', {}).get('lookback_days', 30))
            min_ts = int(time.time()) - (lookback_days * 86400)
        listens = self.fetch_listens(min_ts)
        
        if not listens:
            return 0, []
            
        processed_count = 0
        orphan_scrobbles = []
        latest_ts = min_ts
        
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Pre-load DB tracks for matching
            cursor.execute("SELECT id, artist, title FROM tracks")
            db_tracks = cursor.fetchall()
            
            # Map normalized exact strings and pre-computed word sets
            exact_map = {}
            words_map = {}
            for t_id, t_artist, t_title in db_tracks:
                norm_str = self.normalize_track_string(f"{t_artist} {t_title}")
                exact_map[norm_str] = t_id
                words_map[norm_str] = set(norm_str.split())
                
            # Avoid adding duplicates in the same batch of orphans
            seen_orphans = set()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orphan_scrobbles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artist TEXT,
                    title TEXT,
                    attempts INTEGER DEFAULT 0,
                    UNIQUE(artist, title)
                )
            """)
                
            msid_cache_pairs = []
            for lst in listens:
                ts = lst.get('listened_at')
                if ts > latest_ts:
                    latest_ts = ts
                    
                track_meta = lst.get('track_metadata', {})
                l_artist = track_meta.get('artist_name', '')
                l_title = track_meta.get('track_name', '')
                msid = lst.get('recording_msid')
                if msid and l_artist and l_title:
                    msid_cache_pairs.append((msid, l_artist, l_title))
                
                if not l_artist or not l_title:
                    continue
                
                norm_listen = self.normalize_track_string(f"{l_artist} {l_title}")
                matched_id = None
                
                # Phase 1: Exact Matching (O(1))
                if norm_listen in exact_map:
                    matched_id = exact_map[norm_listen]
                else:
                    # Phase 2: Optimized Fuzzy Fallback with pre-filtering by keywords
                    best_score = 0
                    best_id = None
                    listen_words = set(norm_listen.split())
                    
                    for db_norm, t_id in exact_map.items():
                        # Fast discard if no common words are shared
                        if not (listen_words & words_map[db_norm]):
                            continue
                            
                        score = fuzz.token_set_ratio(norm_listen, db_norm)
                        if score > best_score:
                            best_score = score
                            best_id = t_id
                            if best_score >= 95: # Near perfect match, early stop
                                break
                            
                    if best_score >= self.fuzzy_threshold:
                        matched_id = best_id
                    else:
                        if norm_listen not in seen_orphans and len(orphan_scrobbles) < 20:
                            logger.info(f"Orphan Scrobble detected: '{l_artist} - {l_title}'")
                            orphan_scrobbles.append({'artist': l_artist, 'title': l_title})
                            seen_orphans.add(norm_listen)
                            cursor.execute("INSERT OR IGNORE INTO orphan_scrobbles (artist, title) VALUES (?, ?)", (l_artist, l_title))
                        
                if matched_id:
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                    # Transactional insertion
                    cursor.execute("""
                        UPDATE tracks 
                        SET play_count = play_count + 1, last_played_at = ?, skip_count = 0
                        WHERE id = ?
                    """, (dt, matched_id))
                    
                    cursor.execute("""
                        INSERT INTO listen_events (track_id, listened_at, source)
                        VALUES (?, ?, 'listenbrainz')
                    """, (matched_id, dt))
                    processed_count += 1
            
            # Persist scrobbles to msid_cache
            if msid_cache_pairs:
                cursor.executemany(
                    "INSERT OR REPLACE INTO msid_cache (msid, artist, title) VALUES (?, ?, ?)",
                    msid_cache_pairs
                )

            # Update timestamp for next execution
            if latest_ts > min_ts:
                cursor.execute("INSERT OR REPLACE INTO system_metadata (key, value) VALUES ('last_listenbrainz_sync', ?)", (str(latest_ts),))
                
            conn.commit()

            
        return processed_count, orphan_scrobbles
        
    def is_telemetry_fresh(self) -> bool:
        """Evaluates whether telemetry data is fresh to avoid premature purging."""
        safety_days = self.config.get('conveyor', {}).get('telemetry_safety_margin_days', 7)
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(listened_at) FROM listen_events")
            row = cursor.fetchone()
            if not row or not row[0]:
                return True # Assume fresh if no events exist yet (fresh install)
                
            last_date_str = row[0]
            try:
                last_date = datetime.fromisoformat(last_date_str)
                if last_date.tzinfo is None:
                    last_date = last_date.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                delta = now - last_date
                
                if delta.days > safety_days:
                    logger.warning(f"Outdated telemetry. Last listen was {delta.days} days ago (Margin: {safety_days}). Purging paused.")
                    return False
                return True
            except Exception as e:
                logger.error(f"Error parsing date {last_date_str}: {e}")
                return True
