import os
import logging
import sqlite3
import time
import re
import unicodedata
from datetime import datetime, timezone
import requests
from thefuzz import fuzz
import yaml
from dotenv import load_dotenv

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
        self.base_url = "https://api.listenbrainz.org"
        self.fuzzy_threshold = 85
        
    def normalize_track_string(self, text: str) -> str:
        """Normaliza cadenas eliminando acentos, coletillas y puntuación."""
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
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM system_metadata WHERE key = 'last_listenbrainz_sync'")
            row = cursor.fetchone()
            if row and row[0]:
                return int(row[0])
        return 0

    def set_last_sync_ts(self, ts: int):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO system_metadata (key, value) VALUES ('last_listenbrainz_sync', ?)", (str(ts),))
            conn.commit()

    def fetch_listens(self, min_ts: int) -> list:
        if not self.lb_user:
            logger.error("LISTENBRAINZ_USER no está configurado.")
            return []
            
        headers = {}
        if self.lb_token:
            headers['Authorization'] = f"Token {self.lb_token}"
            
        url = f"{self.base_url}/1/user/{self.lb_user}/listens"
        
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
                        logger.warning("Límite de peticiones alcanzado. Reintentando...")
                        time.sleep(retry_delay * (2 ** attempt))
                    else:
                        logger.error(f"Error HTTP {response.status_code}: {response.text}")
                        break
                except requests.RequestException as e:
                    logger.error(f"Error de red: {e}")
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
            time.sleep(0.5) # Respetar rate-limit de la API (1 req/0.5s aprox)
            
        return all_listens

    def get_loved_tracks(self) -> list[tuple[str, str]]:
        url = f"https://api.listenbrainz.org/1/feedback/user/{self.lb_user}/get-feedback"
        params = {"score": 1, "count": 100}
        headers = {}
        if self.lb_token:
            headers['Authorization'] = f"Token {self.lb_token}"
        try:
            import requests
            r = requests.get(url, headers=headers, params=params)
            if r.status_code == 200:
                data = r.json()
                if not data: data = {}
                feedbacks = data.get('feedback') or []
                
                loved_msids = []
                for item in feedbacks:
                    if not item: continue
                    if item.get('score') == 1 and item.get('recording_msid'):
                        loved_msids.append(item.get('recording_msid'))
                
                if not loved_msids:
                    return []
                    
                # Fetch recent listens to resolve MSIDs
                url_ls = f"https://api.listenbrainz.org/1/user/{self.lb_user}/listens"
                msid_map = {}
                
                max_ts = None
                for _ in range(10): # fetch up to 500 recent listens
                    p = {"count": 100}
                    if max_ts: p["max_ts"] = max_ts
                    r_ls = requests.get(url_ls, params=p)
                    if r_ls.status_code != 200: break
                    ls_data = r_ls.json().get('payload', {}).get('listens', [])
                    if not ls_data: break
                    
                    for lst in ls_data:
                        msid = lst.get('recording_msid')
                        meta = lst.get('track_metadata', {})
                        artist = meta.get('artist_name')
                        title = meta.get('track_name')
                        if msid and artist and title:
                            msid_map[msid] = (artist, title)
                            
                    max_ts = ls_data[-1].get('listened_at') - 1
                
                loved = []
                for msid in loved_msids:
                    if msid in msid_map:
                        loved.append(msid_map[msid])
                        
                return loved
        except Exception as e:
            import logging
            logging.getLogger('engine').error(f"Error fetching loved tracks: {e}")
        return []



    def process_listens(self) -> tuple[int, list]:
        """Descarga scrobbles nuevos, empareja con base de datos y actualiza play_counts.
        Devuelve (cantidad_procesada, lista_huerfanos)."""
        min_ts = self.get_last_sync_ts()
        listens = self.fetch_listens(min_ts)
        
        if not listens:
            return 0, []
            
        processed_count = 0
        orphan_scrobbles = []
        latest_ts = min_ts
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            cursor = conn.cursor()
            
            # Pre-load DB tracks for matching
            cursor.execute("SELECT id, artist, title FROM tracks")
            db_tracks = cursor.fetchall()
            
            # Map normalized exact strings
            exact_map = {}
            for t_id, t_artist, t_title in db_tracks:
                norm_str = self.normalize_track_string(f"{t_artist} {t_title}")
                exact_map[norm_str] = t_id
                
            # Evitar añadir duplicados en la misma tanda de huérfanos
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
                
            for lst in listens:
                ts = lst.get('listened_at')
                if ts > latest_ts:
                    latest_ts = ts
                    
                track_meta = lst.get('track_metadata', {})
                l_artist = track_meta.get('artist_name', '')
                l_title = track_meta.get('track_name', '')
                
                if not l_artist or not l_title:
                    continue
                
                norm_listen = self.normalize_track_string(f"{l_artist} {l_title}")
                matched_id = None
                
                # Fase 1: Emparejamiento Exacto
                if norm_listen in exact_map:
                    matched_id = exact_map[norm_listen]
                else:
                    # Fase 2: Fuzzy Fallback
                    best_score = 0
                    best_id = None
                    for db_norm, t_id in exact_map.items():
                        score = fuzz.token_set_ratio(norm_listen, db_norm)
                        if score > best_score:
                            best_score = score
                            best_id = t_id
                            
                    if best_score >= self.fuzzy_threshold:
                        matched_id = best_id
                    else:
                        if norm_listen not in seen_orphans and len(orphan_scrobbles) < 20:
                            logger.info(f"Scrobble Huérfano detectado: '{l_artist} - {l_title}'")
                            orphan_scrobbles.append({'artist': l_artist, 'title': l_title})
                            seen_orphans.add(norm_listen)
                            cursor.execute("INSERT OR IGNORE INTO orphan_scrobbles (artist, title) VALUES (?, ?)", (l_artist, l_title))
                        
                if matched_id:
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                    # Inserción Transaccional
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
            
            # Actualizar timestamp para próxima ejecución
            if latest_ts > min_ts:
                cursor.execute("INSERT OR REPLACE INTO system_metadata (key, value) VALUES ('last_listenbrainz_sync', ?)", (str(latest_ts),))
                
            conn.commit()
            
        return processed_count, orphan_scrobbles
        
    def is_telemetry_fresh(self) -> bool:
        """Evalúa si los datos de telemetría están recientes para evitar purgas prematuras."""
        safety_days = self.config.get('conveyor', {}).get('telemetry_safety_margin_days', 7)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(listened_at) FROM listen_events")
            row = cursor.fetchone()
            if not row or not row[0]:
                return True # Asumir fresco si no hay eventos (nueva instalación)
                
            last_date_str = row[0]
            try:
                last_date = datetime.fromisoformat(last_date_str)
                if last_date.tzinfo is None:
                    last_date = last_date.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                delta = now - last_date
                
                if delta.days > safety_days:
                    logger.warning(f"Telemetría desactualizada. El último listen fue hace {delta.days} días (Margen: {safety_days}). Purgas pausadas.")
                    return False
                return True
            except Exception as e:
                logger.error(f"Error parseando fecha {last_date_str}: {e}")
                return True
