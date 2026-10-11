import os
import sqlite3
import json
import yaml
import mutagen
import hashlib
import shutil
from src.paths import StoragePaths
from src.db import get_db_connection

class PlaylistGenerator:
    def __init__(self, db_path: str = "data/conveyor_state.sqlite", config_or_storage: str = "config/config.yaml"):
        self.db_path = db_path
        if isinstance(config_or_storage, StoragePaths):
            self.paths = config_or_storage
            self.config_path = "config/config.yaml"
        elif os.path.exists(config_or_storage) and (config_or_storage.endswith('.yaml') or config_or_storage.endswith('.yml')):
            self.paths = StoragePaths(config_or_storage)
            self.config_path = config_or_storage
        else:
            self.paths = StoragePaths("config/config.yaml")
            self.config_path = "config/config.yaml"
            
        self.playlists_dir = self.paths.playlists_dir
        self.artists_dir = os.path.join(self.playlists_dir, "Artistas")
        os.makedirs(self.playlists_dir, exist_ok=True)
        os.makedirs(self.artists_dir, exist_ok=True)
        self.config = self._load_config()
        self.lune_playlists = {}
        self.state_file = "data/playlist_folder_state.json"
        self._meta_cache = {}

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
        Path: Playlists/Permanente.m3u8.
        Sorted alphabetically by Artist -> Album -> Track.
        Registered in Lune backup as 'Permanente'.
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

        m3u8_path = os.path.join(self.playlists_dir, "Permanente.m3u8")
        self._write_playlist(m3u8_path, all_tracks, meta_map, register_for_lune=True, lune_name="Permanente")

        # Clean redundant legacy alias if present
        alias_path = os.path.join(self.playlists_dir, "Canciones_Permanentes.m3u8")
        if os.path.exists(alias_path):
            try:
                os.remove(alias_path)
            except Exception:
                pass

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

        m3u8_path = os.path.join(self.playlists_dir, "Descubrimiento_Prioritario.m3u8")
        self._write_playlist(m3u8_path, tracks, meta_map, register_for_lune=True, lune_name="Descubrimiento Prioritario")

    def generate_cinta_playlists(self, meta_map: dict):
        """
        Generates playlists associated with Conveyor folder:
        1. Cinta.m3u8: All songs currently rotating on Conveyor.
        2. Descubrimiento_Prioritario.m3u8: Unplayed Conveyor tracks (play_count = 0).
        """
        cinta_dir = self.paths.cinta_dir
        cinta_tracks = []
        if os.path.exists(cinta_dir):
            for root, dirs, files in os.walk(cinta_dir):
                dirs.sort()
                for f in sorted(files):
                    if f.endswith(('.opus', '.m4a', '.mp3', '.flac')):
                        cinta_tracks.append(os.path.join(root, f))

        cinta_m3u8 = os.path.join(self.playlists_dir, "Cinta.m3u8")
        self._write_playlist(cinta_m3u8, cinta_tracks, meta_map, register_for_lune=True, lune_name="Cinta")
        self.generate_descubrimiento_prioritario(meta_map)

    def generate_rotacion_viva(self, meta_map: dict):
        """
        Generates smart playlist Rotación Viva:
        - Top 20 most played songs
        - 5 discoveries proportional to favorite genres
        - 5 forgotten permanent songs (> 30 days without play)
        """
        playlist_path = os.path.join(self.playlists_dir, "Rotación_Viva.m3u8")
        
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
            self._write_playlist(playlist_path, all_paths, meta_map, register_for_lune=True, lune_name="Rotación Viva")
            print(f"[PlaylistGenerator] Rotación Viva generated: {len(all_paths)} tracks.")

    def generate_lune_backup(self, meta_map: dict):
        """
        Generates JSON file compatible with Lune native importer (MrDemonc/Lune):
        Playlists/lune_playlists_backup.json
        Structure required by Lune's PlaylistBackupManager:
        {
          "version": 2,
          "playlists": [
            {
              "name": "...",
              "songs": [
                { "title": "...", "artist": "...", "duration": ms, "dateAdded": 0 }
              ]
            }
          ],
          "lyrics": []
        }
        """
        if not self.config.get('playlists', {}).get('generate_lune_backup', True):
            return

        lune_json_path = os.path.join(self.playlists_dir, "lune_playlists_backup.json")
        playlists_data = []

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

        export_data = {
            "version": 2,
            "playlists": playlists_data,
            "lyrics": []
        }

        with open(lune_json_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        print(f"[PlaylistGenerator] Lune playlist backup generated at: {lune_json_path} ({len(playlists_data)} playlists).")

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
        """Loads previous folder fingerprint state saved on disk."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_folder_state(self, perm_fp: str = None, cinta_fp: str = None):
        """Saves current Permanent and Conveyor fingerprints in data/playlist_folder_state.json."""
        state = self._load_folder_state()
        if perm_fp is not None:
            state["permanente_fingerprint"] = perm_fp
        elif "permanente_fingerprint" not in state:
            state["permanente_fingerprint"] = self.get_folder_fingerprint(self.paths.permanente_dir)

        if cinta_fp is not None:
            state["cinta_fingerprint"] = cinta_fp
        elif "cinta_fingerprint" not in state:
            state["cinta_fingerprint"] = self.get_folder_fingerprint(self.paths.cinta_dir)

        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"[PlaylistGenerator] Error saving folder state: {e}")

    def update_permanent_playlists(self, meta_map: dict = None):
        """Updates global Permanent list and artist playlists, syncing Lune."""
        print("[PlaylistGenerator] Updating Permanent playlists...")
        self.lune_playlists = {}
        meta_map = meta_map or self._get_meta_map()
        self.generate_permanent_playlists(meta_map)
        self.generate_cinta_playlists(meta_map)
        self.generate_rotacion_viva(meta_map)
        self.generate_lune_backup(meta_map)
        self._save_folder_state(perm_fp=self.get_folder_fingerprint(self.paths.permanente_dir))

    def update_cinta_playlists(self, meta_map: dict = None):
        """Updates playlists associated with Conveyor folder, syncing Lune."""
        print("[PlaylistGenerator] Updating playlists associated with Conveyor...")
        self.lune_playlists = {}
        meta_map = meta_map or self._get_meta_map()
        self.generate_cinta_playlists(meta_map)
        self.generate_permanent_playlists(meta_map)
        self.generate_rotacion_viva(meta_map)
        self.generate_lune_backup(meta_map)
        self._save_folder_state(cinta_fp=self.get_folder_fingerprint(self.paths.cinta_dir))

    def update_all_playlists(self, meta_map: dict = None):
        """Updates all standard M3U8 playlists and JSON backup for Lune."""
        self.lune_playlists = {}
        meta_map = meta_map or self._get_meta_map()
        self.generate_cinta_playlists(meta_map)
        self.generate_permanent_playlists(meta_map)
        self.generate_rotacion_viva(meta_map)
        self.generate_lune_backup(meta_map)
        self._save_folder_state(
            perm_fp=self.get_folder_fingerprint(self.paths.permanente_dir),
            cinta_fp=self.get_folder_fingerprint(self.paths.cinta_dir)
        )

    def check_and_update_if_modified(self) -> dict:
        """
        Checks whether Permanent or Conveyor directories were physically modified.
        Returns: {'permanente_updated': bool, 'cinta_updated': bool}
        """
        state = self._load_folder_state()
        saved_perm = state.get("permanente_fingerprint", "")
        saved_cinta = state.get("cinta_fingerprint", "")

        curr_perm = self.get_folder_fingerprint(self.paths.permanente_dir)
        curr_cinta = self.get_folder_fingerprint(self.paths.cinta_dir)

        perm_changed = (curr_perm != saved_perm)
        cinta_changed = (curr_cinta != saved_cinta)

        if perm_changed and cinta_changed:
            print("[PlaylistGenerator] Detected changes in both Permanent and Conveyor. Updating all playlists...")
            self.update_all_playlists()
        elif perm_changed:
            print("[PlaylistGenerator] Detected modification in Permanent folder. Updating permanent playlists...")
            self.update_permanent_playlists()
        elif cinta_changed:
            print("[PlaylistGenerator] Detected modification in Conveyor folder. Updating conveyor playlists...")
            self.update_cinta_playlists()

        return {"permanente_updated": perm_changed, "cinta_updated": cinta_changed}
