import os
import re
import unicodedata
import sqlite3
import json
import yaml
import mutagen
import hashlib
import shutil
from src.paths import StoragePaths, sanitize_filename
from src.db import get_db_connection

class PlaylistGenerator:
    def __init__(self, db_path: str = "data/conveyor_state.sqlite", config_or_storage="config/config.yaml"):
        self.db_path = db_path
        if isinstance(config_or_storage, StoragePaths):
            self.paths = config_or_storage
            self.config = getattr(config_or_storage, 'config', {}) or {}
            self.config_path = getattr(config_or_storage, 'config_path', "config/config.yaml")
            if not self.config:
                self.config = self._load_config()
        elif isinstance(config_or_storage, dict):
            self.paths = StoragePaths(config_or_storage)
            self.config = config_or_storage
            self.config_path = "config/config.yaml"
        elif isinstance(config_or_storage, str) and os.path.exists(config_or_storage):
            self.paths = StoragePaths(config_or_storage)
            self.config_path = config_or_storage
            self.config = self._load_config()
        else:
            self.paths = StoragePaths("config/config.yaml")
            self.config_path = "config/config.yaml"
            self.config = self._load_config()
            
        self.playlists_dir = self.paths.playlists_dir
        self.artists_dir = os.path.join(self.playlists_dir, "Artistas")
        
        # User playlists folder inside Playlists/
        self.lune_backup_file = self.config.get('playlists', {}).get('lune_backup_file', "lune_playlists_backup.json")
        self.user_playlists_dir_name = self.config.get('playlists', {}).get('user_playlists_dir', "Listas Propias")
        self.user_playlists_dir = os.path.join(self.playlists_dir, self.user_playlists_dir_name)

        # Configurable English playlist names
        sys_names = self.config.get('playlists', {}).get('system_names', {})
        self.name_permanent = sys_names.get('permanent', 'Permanent')
        self.name_conveyor = sys_names.get('conveyor', 'Conveyor')
        self.name_priority_discovery = sys_names.get('priority_discovery', 'Priority_Discovery')
        self.name_live_rotation = sys_names.get('live_rotation', 'Live_Rotation')
        self.name_cravings = sys_names.get('cravings', 'Cravings')

        os.makedirs(self.playlists_dir, exist_ok=True)
        os.makedirs(self.artists_dir, exist_ok=True)
        os.makedirs(self.user_playlists_dir, exist_ok=True)

        self.lune_playlists = {}
        self.state_file = "data/playlist_folder_state.json"
        self._meta_cache = {}

    def _to_lune_display_name(self, name: str) -> str:
        """Converts underscored filenames to displayable playlist names for Lune."""
        return name.replace("_", " ")

    def _load_config(self) -> dict:
        """Loads configuration from config.yaml if it exists."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
            except Exception:
                return {}
        return {}

    def _get_meta_map(self) -> dict:
        """
        Loads map of file_path -> (artist, title, duration_seconds) from DB.
        If any track has null or <= 0 duration, attempts resolution via Mutagen
        and updates the database so both M3U8 (#EXTINF) and Lune have exact milliseconds.
        """
        meta_map = {}
        updates_to_db = []
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT file_path, artist, title, duration_seconds FROM tracks WHERE file_path IS NOT NULL")
            rows = cursor.fetchall()
            for file_path, artist, title, duration_seconds in rows:
                dur = duration_seconds
                if (dur is None or dur <= 0) and file_path and os.path.exists(file_path):
                    try:
                        audio = mutagen.File(file_path)
                        if audio and getattr(audio, 'info', None) and getattr(audio.info, 'length', None):
                            dur = int(round(audio.info.length))
                            updates_to_db.append((dur, file_path))
                    except Exception:
                        pass
                meta_map[file_path] = (artist, title, dur)

            if updates_to_db:
                cursor.executemany("UPDATE tracks SET duration_seconds = ? WHERE file_path = ?", updates_to_db)
                conn.commit()
                print(f"[PlaylistGenerator] Duration calculated and updated in DB for {len(updates_to_db)} tracks.")

        return meta_map

    def _resolve_track_meta(self, path: str, meta_map: dict = None):
        """
        Retrieves art, tit, dur_seconds, dur_ms for an audio file.
        ABSOLUTE PRIORITY: Direct read of physical file tags using Mutagen.
        Ensures 100% agreement with Android MediaStore and players like Lune.
        Optimization: Uses in-memory _meta_cache to avoid redundant disk reads.
        Fallback: database metadata (meta_map) and filename deduction.
        """
        if path in self._meta_cache:
            return self._meta_cache[path]

        art, tit = None, None
        dur_s, dur_ms = None, None

        if path and os.path.exists(path):
            try:
                audio = mutagen.File(path)
                if audio:
                    # 1. Title from physical tags
                    if 'title' in audio and audio['title']:
                        tit = str(audio['title'][0]).strip()
                    elif '\xa9nam' in audio and audio['\xa9nam']:
                        tit = str(audio['\xa9nam'][0]).strip()
                    elif 'TIT2' in audio and audio['TIT2']:
                        tit = str(audio['TIT2'][0]).strip()

                    # 2. Artist (all collaborators) from physical tags
                    if 'artist' in audio and audio['artist']:
                        art = str(audio['artist'][0]).strip()
                    elif '\xa9ART' in audio and audio['\xa9ART']:
                        art = str(audio['\xa9ART'][0]).strip()
                    elif 'TPE1' in audio and audio['TPE1']:
                        art = str(audio['TPE1'][0]).strip()

                    # 3. Exact duration with milliseconds
                    if getattr(audio, 'info', None) and getattr(audio.info, 'length', None):
                        length = audio.info.length
                        if length > 0:
                            dur_s = int(round(length))
                            dur_ms = int(round(length * 1000))
            except Exception:
                pass

        # Fallback to database if any field is missing
        if meta_map and (not art or not tit or dur_s is None or dur_s <= 0):
            meta = meta_map.get(path)
            if meta:
                db_art, db_tit, db_dur = meta
                if not art and db_art:
                    art = str(db_art).strip()
                if not tit and db_tit:
                    tit = str(db_tit).strip()
                if (dur_s is None or dur_s <= 0) and db_dur and db_dur > 0:
                    dur_s = int(db_dur)
                    if dur_ms is None:
                        dur_ms = int(db_dur * 1000)

        # Fallback by filename
        if not tit and path:
            base = os.path.splitext(os.path.basename(path))[0]
            if ' - ' in base:
                parts = base.split(' - ', 1)
                art = art or parts[0].strip()
                tit = parts[1].strip()
            else:
                tit = base
        if not art:
            art = "Unknown"
        if dur_s is None or dur_s <= 0:
            dur_s = 0
        if dur_ms is None or dur_ms <= 0:
            dur_ms = int(dur_s * 1000)

        res = (art, tit, dur_s, dur_ms)
        self._meta_cache[path] = res
        return res

    def _write_playlist(self, target_file: str, track_paths: list, meta_map: dict = None, register_for_lune: bool = True, lune_name: str = None):
        """Writes standard M3U8 playlist with #EXTINF headers for universal compatibility."""
        target_dir = os.path.dirname(target_file)
        os.makedirs(target_dir, exist_ok=True)
        valid_paths = []
        with open(target_file, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            for p in track_paths:
                if not p or not os.path.exists(p):
                    continue
                valid_paths.append(p)
                art, tit, dur_s, _ = self._resolve_track_meta(p, meta_map)
                dur_val = dur_s if dur_s > 0 else -1
                display = f"{art} - {tit}" if art and tit and art != "Unknown" else tit
                    
                f.write(f"#EXTINF:{dur_val},{display}\n")
                rel_p = os.path.relpath(p, target_dir)
                f.write(f"{rel_p}\n")

        if register_for_lune and valid_paths:
            name = lune_name or os.path.splitext(os.path.basename(target_file))[0].replace("_", " ")
            self.lune_playlists[name] = valid_paths
        
    def generate_all_permanent_playlist(self, meta_map: dict) -> list[str]:
        """
        Generates M3U8 playlist with all permanent tracks in the collection.
        Path: Playlists/<name_permanent>.m3u8 (e.g. Permanent.m3u8).
        Sorted alphabetically by Artist -> Album -> Track.
        """
        permanente_dir = self.paths.permanente_dir
        if not os.path.exists(permanente_dir):
            return []

        all_tracks = []
        for root, dirs, files in os.walk(permanente_dir):
            dirs.sort()
            for f in sorted(files):
                if f.endswith(('.opus', '.m4a', '.mp3', '.flac')):
                    all_tracks.append(os.path.join(root, f))

        m3u8_path = os.path.join(self.playlists_dir, f"{self.name_permanent}.m3u8")
        lune_name = self._to_lune_display_name(self.name_permanent)
        self._write_playlist(m3u8_path, all_tracks, meta_map, register_for_lune=True, lune_name=lune_name)

        print(f"[PlaylistGenerator] All permanent tracks playlist generated: {len(all_tracks)} tracks in {m3u8_path}")
        return all_tracks

    @staticmethod
    def split_artists(artist_str: str) -> list[str]:
        """
        Splits artist string into individual artists.
        Recognizes common delimiters: ',', ';', '/', '&', 'feat.', 'ft.', 'con', 'with', ' x '.
        """
        if not artist_str:
            return []
        import re
        cleaned = re.sub(r'\b(?:feat|ft|con|with)\.?\b', ',', artist_str, flags=re.IGNORECASE)
        tokens = re.split(r'[,;/&]|\s+[xX]\s+', cleaned)
        artists = []
        for t in tokens:
            item = t.strip()
            if item and item not in artists:
                artists.append(item)
        return artists if artists else [artist_str.strip()]

    def generate_artist_playlists(self, meta_map: dict):
        """
        Generates playlists for Permanent collection organized by Artist (<Artist>.m3u8).
        INCLUSIVE: Includes both solo tracks and guest collaborations (feat / remix).
        """
        permanente_dir = self.paths.permanente_dir
        if not os.path.exists(permanente_dir):
            return

        include_artists_lune = self.config.get('playlists', {}).get('lune_include_artists', False)
        min_tracks = int(self.config.get('playlists', {}).get('min_artist_tracks', 10))
        main_artists = [a for a in sorted(os.listdir(permanente_dir)) if os.path.isdir(os.path.join(permanente_dir, a))]

        # Mapping artist -> list of track paths
        artist_songs = {a: [] for a in main_artists}
        artist_lower_map = {a.lower(): a for a in main_artists}

        # Traverse entire Permanent collection to assign collaborations
        for root, dirs, files in os.walk(permanente_dir):
            dirs.sort()
            for f in sorted(files):
                if f.endswith(('.opus', '.m4a', '.mp3', '.flac')):
                    full_p = os.path.join(root, f)
                    art, tit, _, _ = self._resolve_track_meta(full_p, meta_map)
                    
                    # Split all participating artists
                    all_artists = self.split_artists(art)
                    for a in all_artists:
                        canon_a = artist_lower_map.get(a.lower(), a if a in artist_songs else None)
                        if canon_a:
                            if canon_a not in artist_songs:
                                artist_songs[canon_a] = []
                            if full_p not in artist_songs[canon_a]:
                                artist_songs[canon_a].append(full_p)

        active_playlist_files = set()
        for artist, tracks in artist_songs.items():
            if len(tracks) >= min_tracks:
                # Sort alphabetically by relative path (Album -> Track)
                tracks.sort()
                fname = f"{artist}.m3u8"
                active_playlist_files.add(fname)
                m3u8_path = os.path.join(self.artists_dir, fname)
                self._write_playlist(m3u8_path, tracks, meta_map, register_for_lune=include_artists_lune, lune_name=artist)

        # Clean legacy playlists in Artistas/ that no longer meet the threshold
        if os.path.exists(self.artists_dir):
            for existing_f in os.listdir(self.artists_dir):
                if existing_f.endswith('.m3u8') and existing_f not in active_playlist_files:
                    try:
                        os.remove(os.path.join(self.artists_dir, existing_f))
                    except Exception:
                        pass

    def generate_permanent_playlists(self, meta_map: dict):
        """
        Generates all playlists for the Permanent collection:
        1. Global playlist of all permanent tracks (Permanente.m3u8).
        2. Dedicated individual artist playlists (<Artist>.m3u8).
        """
        self.generate_all_permanent_playlist(meta_map)
        self.generate_artist_playlists(meta_map)

    def generate_descubrimiento_prioritario(self, meta_map: dict):
        """Generates M3U8 with unplayed tracks currently on Conveyor (play_count = 0)."""
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT file_path FROM tracks
                WHERE status = 'CINTA' AND play_count = 0 AND file_path IS NOT NULL
                ORDER BY added_at ASC
            """)
            tracks = [r[0] for r in cursor.fetchall()]

        m3u8_path = os.path.join(self.playlists_dir, f"{self.name_priority_discovery}.m3u8")
        lune_name = self._to_lune_display_name(self.name_priority_discovery)
        self._write_playlist(m3u8_path, tracks, meta_map, register_for_lune=True, lune_name=lune_name)

    def generate_cinta_playlists(self, meta_map: dict):
        """
        Generates playlists associated with Conveyor folder:
        1. <name_conveyor>.m3u8: All songs currently rotating on Conveyor.
        2. <name_priority_discovery>.m3u8: Unplayed Conveyor tracks (play_count = 0).
        """
        cinta_dir = self.paths.cinta_dir
        cinta_tracks = []
        if os.path.exists(cinta_dir):
            for root, dirs, files in os.walk(cinta_dir):
                dirs.sort()
                for f in sorted(files):
                    if f.endswith(('.opus', '.m4a', '.mp3', '.flac')):
                        cinta_tracks.append(os.path.join(root, f))

        cinta_m3u8 = os.path.join(self.playlists_dir, f"{self.name_conveyor}.m3u8")
        lune_name = self._to_lune_display_name(self.name_conveyor)
        self._write_playlist(cinta_m3u8, cinta_tracks, meta_map, register_for_lune=True, lune_name=lune_name)
        self.generate_descubrimiento_prioritario(meta_map)

    def generate_cravings_playlist(self, meta_map: dict):
        """
        Generates playlist for Cravings / Antojos:
        Playlists/<name_cravings>.m3u8 (e.g. Playlists/Cravings.m3u8).
        """
        cravings_dir = getattr(self.paths, 'cravings_dir', None)
        if not cravings_dir or not os.path.exists(cravings_dir):
            return

        cravings_tracks = []
        for root, dirs, files in os.walk(cravings_dir):
            dirs.sort()
            for f in sorted(files):
                if f.endswith(('.opus', '.m4a', '.mp3', '.flac')):
                    cravings_tracks.append(os.path.join(root, f))

        playlist_path = os.path.join(self.playlists_dir, f"{self.name_cravings}.m3u8")
        lune_name = self._to_lune_display_name(self.name_cravings)
        self._write_playlist(playlist_path, cravings_tracks, meta_map, register_for_lune=True, lune_name=lune_name)

    def generate_rotacion_viva(self, meta_map: dict):
        """
        Generates smart playlist Live Rotation / Rotación Viva:
        - Top 20 most played songs
        - 5 discoveries proportional to favorite genres
        - 5 forgotten permanent songs (> 30 days without play)
        """
        playlist_path = os.path.join(self.playlists_dir, f"{self.name_live_rotation}.m3u8")
        
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 1. Top 20 tracks (most played)
            cursor.execute('''
                SELECT t.id, t.file_path, t.genre
                FROM tracks t
                JOIN listen_events e ON t.id = e.track_id
                WHERE t.file_path IS NOT NULL
                GROUP BY t.id
                ORDER BY COUNT(e.id) DESC
                LIMIT 20
            ''')
            top_20 = cursor.fetchall()
            
            if not top_20:
                cursor.execute('''
                    SELECT id, file_path, genre
                    FROM tracks
                    WHERE file_path IS NOT NULL AND status IN ('PERMANENT', 'CINTA')
                    ORDER BY play_count DESC
                    LIMIT 20
                ''')
                top_20 = cursor.fetchall()
                
            if not top_20:
                return
                
            top_ids = [t[0] for t in top_20]
            top_paths = [t[1] for t in top_20 if t[1] and os.path.exists(t[1])]
            
            # Genre distribution
            genre_counts = {}
            for t in top_20:
                g = t[2] or "Unknown"
                genre_counts[g] = genre_counts.get(g, 0) + 1
                
            # 2. Discoveries (5 tracks matching genre proportions)
            discovery_paths = []
            top_20_len = len(top_20)
            
            for g, count in genre_counts.items():
                limit = round((count / top_20_len) * 5)
                if limit > 0:
                    primary_g = g.split('/')[0].strip()
                    cursor.execute(f'''
                        SELECT file_path FROM tracks 
                        WHERE (genre LIKE ? OR genre = ?) AND status = 'CINTA' 
                        AND file_path IS NOT NULL
                        AND id NOT IN ({','.join(['?']*len(top_ids))})
                        ORDER BY RANDOM() LIMIT ?
                    ''', [f"%{primary_g}%", g] + top_ids + [limit])
                    discovery_paths.extend([r[0] for r in cursor.fetchall() if r[0] and os.path.exists(r[0])])

            # 3. Forgotten (5 permanent tracks with > 30 days without play)
            cursor.execute(f'''
                SELECT file_path FROM tracks 
                WHERE status = 'PERMANENT' AND file_path IS NOT NULL
                AND id NOT IN ({','.join(['?']*len(top_ids))})
                AND id NOT IN (
                    SELECT track_id FROM listen_events 
                    WHERE listened_at > datetime('now', '-30 days')
                )
                ORDER BY RANDOM() LIMIT 5
            ''', top_ids)
            forgotten_paths = [r[0] for r in cursor.fetchall() if r[0] and os.path.exists(r[0])]
            
            all_paths = top_paths + discovery_paths + forgotten_paths
            lune_name = self._to_lune_display_name(self.name_live_rotation)
            self._write_playlist(playlist_path, all_paths, meta_map, register_for_lune=True, lune_name=lune_name)
            print(f"[PlaylistGenerator] {self.name_live_rotation} generated: {len(all_paths)} tracks in {playlist_path}")

    # --------------------------------------------------------------------------
    # LUNE BACKUP RESOLUTION & USER PLAYLIST EXTRACTION
    # --------------------------------------------------------------------------
    def _normalize_for_match(self, s: str) -> str:
        """Normalizes strings for reliable matching (lowercased, unaccented, alphanumeric)."""
        if not s:
            return ""
        norm_s = unicodedata.normalize('NFKD', str(s))
        norm_s = "".join(c for c in norm_s if not unicodedata.combining(c))
        norm_s = norm_s.lower().strip()
        norm_s = re.sub(r'[\(\)\[\]\{\}\.,:;!?\"\x27_\-]', ' ', norm_s)
        return re.sub(r'\s+', ' ', norm_s).strip()

    def _clean_song_title(self, s: str) -> str:
        """Strips secondary parenthetical information or promotional tags from title."""
        if not s:
            return ""
        cleaned = re.sub(r'\(.*?\)|\[.*?\]', '', str(s))
        cleaned = re.sub(r'\b(?:feat|ft|remix|prod|prod by|audio oficial|video oficial|official audio|official video|lyric video|letra)\b.*', '', cleaned, flags=re.IGNORECASE)
        return self._normalize_for_match(cleaned)

    def _build_song_resolver_index(self, meta_map: dict) -> dict:
        """
        Builds a multi-tiered in-memory index of all existing local audio files on disk
        to map Lune backup metadata (title, artist, duration) to local files.
        """
        exact_index = {}       # (norm_art, norm_tit) -> (file_path, dur_ms)
        title_index = {}       # norm_tit -> list of (norm_art, split_arts, file_path, dur_ms)
        clean_title_index = {} # clean_tit -> list of (norm_art, split_arts, file_path, dur_ms)
        seen_paths = set()

        # 1. Query database for known active tracks
        try:
            with get_db_connection(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT file_path, artist, title, duration_seconds 
                    FROM tracks 
                    WHERE file_path IS NOT NULL AND status != 'PURGED'
                """)
                for f_path, art, tit, dur_s in cursor.fetchall():
                    if f_path and os.path.exists(f_path):
                        seen_paths.add(f_path)
                        dur_ms = int(dur_s * 1000) if dur_s else 0
                        self._add_to_resolver_indexes(exact_index, title_index, clean_title_index, f_path, art, tit, dur_ms)
        except Exception:
            pass

        # 2. Query meta_map for any additional tracks on disk
        if meta_map:
            for f_path, (art, tit, dur_s) in meta_map.items():
                if f_path and f_path not in seen_paths and os.path.exists(f_path):
                    seen_paths.add(f_path)
                    dur_ms = int(dur_s * 1000) if dur_s else 0
                    self._add_to_resolver_indexes(exact_index, title_index, clean_title_index, f_path, art, tit, dur_ms)

        return {
            "exact": exact_index,
            "title": title_index,
            "clean_title": clean_title_index
        }

    def _add_to_resolver_indexes(self, exact_index: dict, title_index: dict, clean_title_index: dict,
                                 file_path: str, artist: str, title: str, dur_ms: int):
        n_art = self._normalize_for_match(artist)
        n_tit = self._normalize_for_match(title)
        split_arts = [self._normalize_for_match(a) for a in self.split_artists(artist)]

        entry = (n_art, split_arts, file_path, dur_ms)
        exact_index[(n_art, n_tit)] = (file_path, dur_ms)
        title_index.setdefault(n_tit, []).append(entry)

        c_tit = self._clean_song_title(title)
        if c_tit:
            clean_title_index.setdefault(c_tit, []).append(entry)

    def _pick_best_candidate(self, candidates: list, n_art: str, lune_split_arts: list, lune_dur_ms: int) -> tuple[str | None, int]:
        if not candidates:
            return None, 0

        matching_artist = []
        for cand_art, cand_splits, cand_path, cand_dur in candidates:
            if not os.path.exists(cand_path):
                continue
            if n_art and (n_art in cand_art or cand_art in n_art):
                matching_artist.append((cand_path, cand_dur))
                continue
            if any(sa in cand_splits for sa in lune_split_arts if sa):
                matching_artist.append((cand_path, cand_dur))
                continue
            if any(ca in lune_split_arts for ca in cand_splits if ca):
                matching_artist.append((cand_path, cand_dur))
                continue

        pool = matching_artist if matching_artist else [(c[2], c[3]) for c in candidates if os.path.exists(c[2])]
        if not pool:
            return None, 0

        if len(pool) == 1:
            return pool[0]

        if lune_dur_ms > 0:
            pool.sort(key=lambda item: abs(item[1] - lune_dur_ms))
        return pool[0]

    def resolve_lune_song(self, song: dict, index: dict) -> tuple[str | None, int]:
        """
        Resolves a song dictionary from Lune backup to an existing local physical audio file.
        Returns (file_path, duration_ms) if found and physically present, or (None, 0).
        """
        raw_title = song.get("title", "")
        raw_artist = song.get("artist", "")
        lune_dur_ms = song.get("duration", 0)

        n_tit = self._normalize_for_match(raw_title)
        n_art = self._normalize_for_match(raw_artist)

        # 1. Exact match on (artist, title)
        exact_match = index["exact"].get((n_art, n_tit))
        if exact_match and os.path.exists(exact_match[0]):
            return exact_match[0], exact_match[1] or lune_dur_ms

        # 2. Normalized title match with artist overlap
        lune_split_arts = [self._normalize_for_match(a) for a in self.split_artists(raw_artist)]
        candidates = index["title"].get(n_tit, [])
        best_path, best_dur = self._pick_best_candidate(candidates, n_art, lune_split_arts, lune_dur_ms)
        if best_path:
            return best_path, best_dur or lune_dur_ms

        # 3. Cleaned title match
        c_tit = self._clean_song_title(raw_title)
        if c_tit:
            clean_candidates = index["clean_title"].get(c_tit, [])
            best_path, best_dur = self._pick_best_candidate(clean_candidates, n_art, lune_split_arts, lune_dur_ms)
            if best_path:
                return best_path, best_dur or lune_dur_ms

        return None, 0

    def get_system_playlist_names(self) -> set[str]:
        """Returns set of normalized names that represent system-generated playlists."""
        names = {
            "permanent", "permanente",
            "conveyor", "cinta",
            "priority discovery", "priority_discovery", "descubrimiento prioritario", "descubrimiento_prioritario",
            "live rotation", "live_rotation", "rotacion viva", "rotación viva", "rotacion_viva", "rotación_viva",
            "cravings", "antojos"
        }
        for n in [self.name_permanent, self.name_conveyor, self.name_priority_discovery, self.name_live_rotation, self.name_cravings]:
            if n:
                names.add(self._normalize_for_match(n))
                names.add(self._normalize_for_match(n.replace("_", " ")))
        return names

    def get_known_artist_names(self) -> set[str]:
        """Returns set of artist names that have dedicated automatic artist playlists."""
        known = set()
        perm_dir = self.paths.permanente_dir
        if os.path.exists(perm_dir):
            for entry in os.listdir(perm_dir):
                if os.path.isdir(os.path.join(perm_dir, entry)):
                    known.add(self._normalize_for_match(entry))
        if os.path.exists(self.artists_dir):
            for entry in os.listdir(self.artists_dir):
                if entry.endswith('.m3u8'):
                    base = os.path.splitext(entry)[0]
                    known.add(self._normalize_for_match(base))
        return known

    def is_user_playlist(self, name: str, system_names: set[str], known_artists: set[str]) -> bool:
        """Determines if a playlist from Lune backup was created by the user."""
        norm_name = self._normalize_for_match(name)
        if not norm_name:
            return False
        if norm_name in system_names:
            return False
        include_artists = self.config.get('playlists', {}).get('lune_include_artists', True)
        if include_artists and norm_name in known_artists:
            return False
        return True

    def sync_lune_user_playlists(self, meta_map: dict = None, resolver_index: dict = None) -> dict[str, list[dict]]:
        """
        Extracts user-created playlists from Lune backup JSON file:
        - Resolves each song against physically existing local files.
        - Removes deleted/missing songs from the playlist.
        - Generates/updates .m3u8 playlists inside Playlists/Listas Propias/ (user_playlists_dir).
        - Cleans obsolete .m3u8 files in user_playlists_dir if removed from Lune.
        Returns: mapping of playlist_name -> list of cleaned song dicts to preserve in Lune JSON backup.
        """
        lune_json_path = os.path.join(self.playlists_dir, self.lune_backup_file)
        if not os.path.exists(lune_json_path):
            return {}

        try:
            with open(lune_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"[PlaylistGenerator] Warning: Could not read Lune backup JSON ({lune_json_path}): {e}")
            return {}

        raw_playlists = data.get('playlists', [])
        if not raw_playlists:
            return {}

        system_names = self.get_system_playlist_names()
        known_artists = self.get_known_artist_names()

        meta_map = meta_map or self._get_meta_map()
        resolver_index = resolver_index or self._build_song_resolver_index(meta_map)

        os.makedirs(self.user_playlists_dir, exist_ok=True)
        user_playlists_cleaned = {}
        active_m3u8_files = set()

        for pl in raw_playlists:
            pl_name = pl.get('name', '').strip()
            if not pl_name:
                continue

            if not self.is_user_playlist(pl_name, system_names, known_artists):
                continue

            valid_paths = []
            cleaned_songs = []

            for song in pl.get('songs', []):
                f_path, dur_ms = self.resolve_lune_song(song, resolver_index)
                if f_path and os.path.exists(f_path):
                    valid_paths.append(f_path)
                    art, tit, _, real_ms = self._resolve_track_meta(f_path, meta_map)
                    cleaned_songs.append({
                        "title": tit or song.get("title", ""),
                        "artist": art or song.get("artist", ""),
                        "duration": real_ms or dur_ms or song.get("duration", 0),
                        "dateAdded": song.get("dateAdded", 0)
                    })

            safe_name = sanitize_filename(pl_name)
            m3u8_filename = f"{safe_name}.m3u8"
            active_m3u8_files.add(m3u8_filename)
            m3u8_path = os.path.join(self.user_playlists_dir, m3u8_filename)

            if valid_paths:
                self._write_playlist(m3u8_path, valid_paths, meta_map, register_for_lune=False)
                user_playlists_cleaned[pl_name] = cleaned_songs
                print(f"[PlaylistGenerator] User playlist '{pl_name}' synced: {len(valid_paths)} tracks -> {m3u8_path}")
            else:
                if os.path.exists(m3u8_path):
                    try:
                        os.remove(m3u8_path)
                    except Exception:
                        pass

        # Clean obsolete user playlists in user_playlists_dir no longer present in Lune backup
        if os.path.exists(self.user_playlists_dir):
            for f in os.listdir(self.user_playlists_dir):
                if f.endswith('.m3u8') and f not in active_m3u8_files:
                    try:
                        os.remove(os.path.join(self.user_playlists_dir, f))
                        print(f"[PlaylistGenerator] Removed deleted user playlist: {f}")
                    except Exception:
                        pass

        return user_playlists_cleaned

    def _clean_legacy_playlists(self):
        """
        Cleans legacy Spanish-named .m3u8 playlists from playlists_dir
        when English names or custom configured names are active.
        """
        configured_m3u8_names = {
            f"{self.name_permanent}.m3u8",
            f"{self.name_conveyor}.m3u8",
            f"{self.name_priority_discovery}.m3u8",
            f"{self.name_live_rotation}.m3u8",
            f"{self.name_cravings}.m3u8",
        }
        legacy_candidates = [
            "Permanente.m3u8", "Canciones_Permanentes.m3u8",
            "Cinta.m3u8",
            "Descubrimiento_Prioritario.m3u8",
            "Rotación_Viva.m3u8", "Rotacion_Viva.m3u8",
            "Antojos.m3u8"
        ]
        for leg in legacy_candidates:
            if leg not in configured_m3u8_names:
                leg_path = os.path.join(self.playlists_dir, leg)
                if os.path.exists(leg_path):
                    try:
                        os.remove(leg_path)
                        print(f"[PlaylistGenerator] Removed legacy Spanish playlist: {leg}")
                    except Exception:
                        pass

    def generate_lune_backup(self, meta_map: dict, user_playlists: dict = None):
        """
        Generates or updates JSON file compatible with Lune native importer (MrDemonc/Lune):
        Playlists/<lune_backup_file> (default: lune_playlists_backup.json).
        Combines system playlists, updated artist playlists, and preserved user playlists,
        filtering out any songs that were deleted from disk.
        """
        if not self.config.get('playlists', {}).get('generate_lune_backup', False):
            return

        lune_json_path = os.path.join(self.playlists_dir, self.lune_backup_file)

        # If user_playlists was not provided, extract and clean it from existing backup
        if user_playlists is None:
            user_playlists = self.sync_lune_user_playlists(meta_map)

        playlists_data = []

        # 1. Registered system playlists and artist playlists
        for name, track_paths in self.lune_playlists.items():
            songs_list = []
            for p in track_paths:
                if not p or not os.path.exists(p):
                    continue
                art, tit, dur_s, dur_ms = self._resolve_track_meta(p, meta_map)
                songs_list.append({
                    "title": str(tit).strip(),
                    "artist": str(art).strip(),
                    "duration": dur_ms,
                    "dateAdded": 0
                })

            if songs_list:
                playlists_data.append({
                    "name": name,
                    "songs": songs_list
                })

        # 2. Append preserved user playlists (already verified and cleaned of deleted tracks)
        if user_playlists:
            for u_name, u_songs in user_playlists.items():
                if u_songs:
                    playlists_data.append({
                        "name": u_name,
                        "songs": u_songs
                    })

        export_data = {
            "version": 2,
            "playlists": playlists_data,
            "lyrics": []
        }

        try:
            with open(lune_json_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            print(f"[PlaylistGenerator] Lune playlist backup updated at: {lune_json_path} ({len(playlists_data)} playlists total).")
        except Exception as e:
            print(f"[PlaylistGenerator] Error writing Lune playlist backup: {e}")

    def get_lune_backup_fingerprint(self) -> str:
        """Calculates deterministic sha256 hash of the Lune backup JSON file."""
        lune_path = os.path.join(self.playlists_dir, self.lune_backup_file)
        if not os.path.exists(lune_path):
            return ""
        try:
            with open(lune_path, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception:
            return ""

    def get_folder_fingerprint(self, folder_path: str) -> str:
        """Calculates deterministic fast fingerprint based on audio files, mtimes, and sizes."""
        if not os.path.exists(folder_path):
            return ""
        entries = []
        for root, _, files in os.walk(folder_path):
            for f in files:
                if f.endswith(('.opus', '.m4a', '.mp3', '.flac')):
                    full_p = os.path.join(root, f)
                    try:
                        st = os.stat(full_p)
                        rel = os.path.relpath(full_p, folder_path)
                        entries.append(f"{rel}:{st.st_mtime_ns}:{st.st_size}")
                    except OSError:
                        pass
        entries.sort()
        return hashlib.sha256(";".join(entries).encode("utf-8")).hexdigest()

    def _load_folder_state(self) -> dict:
        """Loads previous folder and Lune backup fingerprint state saved on disk."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_folder_state(self, perm_fp: str = None, cinta_fp: str = None, cravings_fp: str = None, lune_fp: str = None):
        """Saves current Permanent, Conveyor, Cravings, and Lune backup fingerprints in data/playlist_folder_state.json."""
        state = self._load_folder_state()
        if perm_fp is not None:
            state["permanente_fingerprint"] = perm_fp
        elif "permanente_fingerprint" not in state:
            state["permanente_fingerprint"] = self.get_folder_fingerprint(self.paths.permanente_dir)

        if cinta_fp is not None:
            state["cinta_fingerprint"] = cinta_fp
        elif "cinta_fingerprint" not in state:
            state["cinta_fingerprint"] = self.get_folder_fingerprint(self.paths.cinta_dir)

        if cravings_fp is not None:
            state["cravings_fingerprint"] = cravings_fp
        elif "cravings_fingerprint" not in state and hasattr(self.paths, 'cravings_dir'):
            state["cravings_fingerprint"] = self.get_folder_fingerprint(self.paths.cravings_dir)

        if lune_fp is not None:
            state["lune_backup_fingerprint"] = lune_fp
        else:
            state["lune_backup_fingerprint"] = self.get_lune_backup_fingerprint()

        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"[PlaylistGenerator] Error saving folder state: {e}")

    def update_permanent_playlists(self, meta_map: dict = None):
        """Updates global Permanent list, artist playlists, cravings, and Lune backup."""
        print("[PlaylistGenerator] Updating Permanent playlists...")
        self.update_all_playlists(meta_map=meta_map)

    def update_cinta_playlists(self, meta_map: dict = None):
        """Updates Conveyor playlists, cravings, and Lune backup."""
        print("[PlaylistGenerator] Updating Conveyor playlists...")
        self.update_all_playlists(meta_map=meta_map)

    def update_all_playlists(self, meta_map: dict = None):
        """
        Updates all standard M3U8 playlists (in English), extracts and syncs Lune user playlists
        into user_playlists_dir, cleans legacy playlists, and updates Lune JSON backup.
        """
        self.lune_playlists = {}
        meta_map = meta_map or self._get_meta_map()
        resolver = self._build_song_resolver_index(meta_map)

        # 1. Sync user-created playlists from Lune backup
        user_playlists = self.sync_lune_user_playlists(meta_map, resolver)

        # 2. Generate standard system playlists in English
        self.generate_cinta_playlists(meta_map)
        self.generate_permanent_playlists(meta_map)
        self.generate_cravings_playlist(meta_map)
        self.generate_rotacion_viva(meta_map)

        # 3. Clean legacy Spanish playlist files if English names are active
        self._clean_legacy_playlists()

        # 4. Generate refreshed Lune backup combining system, artists, and clean user playlists
        self.generate_lune_backup(meta_map, user_playlists=user_playlists)

        # 5. Save updated state fingerprints
        crav_fp = self.get_folder_fingerprint(self.paths.cravings_dir) if hasattr(self.paths, 'cravings_dir') else ""
        self._save_folder_state(
            perm_fp=self.get_folder_fingerprint(self.paths.permanente_dir),
            cinta_fp=self.get_folder_fingerprint(self.paths.cinta_dir),
            cravings_fp=crav_fp,
            lune_fp=self.get_lune_backup_fingerprint()
        )

    def check_and_update_if_modified(self) -> dict:
        """
        Checks whether Permanent, Conveyor, Cravings directories or the Lune backup file were modified.
        Returns: {'permanente_updated': bool, 'cinta_updated': bool, 'cravings_updated': bool, 'lune_updated': bool}
        """
        if not self.config.get('playlists', {}).get('auto_update_on_change', True):
            return {"permanente_updated": False, "cinta_updated": False, "cravings_updated": False, "lune_updated": False}

        state = self._load_folder_state()
        saved_perm = state.get("permanente_fingerprint", "")
        saved_cinta = state.get("cinta_fingerprint", "")
        saved_cravings = state.get("cravings_fingerprint", "")
        saved_lune = state.get("lune_backup_fingerprint", "")

        curr_perm = self.get_folder_fingerprint(self.paths.permanente_dir)
        curr_cinta = self.get_folder_fingerprint(self.paths.cinta_dir)
        curr_cravings = self.get_folder_fingerprint(self.paths.cravings_dir) if hasattr(self.paths, 'cravings_dir') else ""
        curr_lune = self.get_lune_backup_fingerprint()

        perm_changed = (curr_perm != saved_perm)
        cinta_changed = (curr_cinta != saved_cinta)
        cravings_changed = (curr_cravings != saved_cravings)
        lune_changed = (bool(curr_lune) and curr_lune != saved_lune)

        if perm_changed or cinta_changed or cravings_changed or lune_changed:
            reasons = []
            if perm_changed:
                reasons.append("Permanent folder")
            if cinta_changed:
                reasons.append("Conveyor folder")
            if cravings_changed:
                reasons.append("Cravings folder")
            if lune_changed:
                reasons.append("Lune backup file")
            print(f"[PlaylistGenerator] Detected changes in: {', '.join(reasons)}. Updating all playlists...")
            self.update_all_playlists()

        return {
            "permanente_updated": perm_changed,
            "cinta_updated": cinta_changed,
            "cravings_updated": cravings_changed,
            "lune_updated": lune_changed
        }

