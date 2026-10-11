import os
import json
import re
import logging
from collections import Counter
from ytmusicapi import YTMusic
from src.paths import StoragePaths, sanitize_filename
from src.album_resolver import resolve_album_track, get_primary_artist
from src.db import get_db_connection

logger = logging.getLogger('ytm_extractor')

class YTMExtractor:
    def __init__(self, db_path: str = "data/conveyor_state.sqlite", config_path: str = "config/config.yaml", auth_file: str = "config/headers_auth.json"):
        self.db_path = db_path
        self.paths = StoragePaths(config_path)
        self.paths.ensure_dirs()
        
        if os.path.exists(auth_file):
            self.yt = YTMusic(auth_file)
        else:
            self.yt = YTMusic()
            
    def sanitize_filename(self, name: str) -> str:
        return sanitize_filename(name)

    def import_from_local_database(self, db_json_path: str = "../Herramientas/Sincronizador_YT/registros/base_datos.json", csv_path: str = "../Herramientas/Sincronizador_YT/datos/lista.csv"):
        """
        Imports matched tracks cross-referencing YouTube video_id with
        clean canonical Spotify metadata (lista.csv).
        Ensures artist is the true recording artist and NOT the YouTube channel/uploader.
        """
        import csv

        if not os.path.exists(db_json_path):
            raise FileNotFoundError(f"Local file not found: {db_json_path}")
            
        print(f"Loading local catalog from {db_json_path}...")
        with open(db_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        def norm_key(texto):
            if not texto:
                return ''
            t = str(texto).lower()
            t = re.sub(r'\(.*?\)|\[.*?\]', '', t)
            t = re.sub(r'[^a-z0-9áéíóúñ\s]', ' ', t)
            t = re.sub(r'\b(official|video|audio|remix|feat|ft|lyrics)\b', '', t)
            return ' '.join(t.split())

        csv_metadata = {}
        if os.path.exists(csv_path):
            print(f"Cross-referencing official canonical metadata from {csv_path}...")
            with open(csv_path, 'r', encoding='utf-8') as cf:
                sample = cf.read(1024)
                cf.seek(0)
                delimiter = ';' if ';' in sample else ','
                for row in csv.DictReader(cf, delimiter=delimiter):
                    t_orig = (row.get("Track Name") or row.get("Title") or row.get("Nombre de la canción") or "").strip()
                    a_orig = (row.get("Artist Name(s)") or row.get("Artist") or row.get("Nombre(s) del artista") or "").strip()
                    album_orig = (row.get("Album Name") or row.get("Album") or row.get("Nombre del álbum") or "").strip()
                    
                    if t_orig and a_orig:
                        a_primary = get_primary_artist(a_orig)
                        meta_item = {
                            'artist': a_orig,
                            'primary_artist': a_primary,
                            'title': t_orig,
                            'album': album_orig or "Singles"
                        }
                        csv_metadata[f"{t_orig.lower()}||{norm_key(a_primary)}"] = meta_item
                        csv_metadata[f"{t_orig.lower()}||{norm_key(a_orig)}"] = meta_item
                        csv_metadata[t_orig.lower()] = meta_item
            
        found_tracks = [(k, v) for k, v in data.items() if v.get('status') == 'FOUND' and v.get('video_id')]
        total_tracks = len(found_tracks)
        print(f"Found {total_tracks} valid tracks with video_id.")
        print("Assigning hierarchy Permanent/<Primary_Artist>/<Album>/...")
        
        extracted = []
        for idx, (db_key, t) in enumerate(found_tracks, start=1):
            vid = t.get('video_id')
            yt_title = t.get('yt_title', 'Unknown Title')
            yt_artist = t.get('yt_artist', 'Unknown Artist')
            yt_album = t.get('yt_album') or "Singles"
            
            # Lookup in clean CSV metadata
            clean_meta = (
                csv_metadata.get(db_key.lower()) or
                csv_metadata.get(f"{yt_title.lower()}||{norm_key(yt_artist)}") or
                csv_metadata.get(yt_title.lower())
            )
            
            if clean_meta:
                full_artist = clean_meta['artist']
                primary_artist = clean_meta['primary_artist']
                title = clean_meta['title']
                album = clean_meta['album']
            else:
                full_artist = yt_artist
                primary_artist = get_primary_artist(yt_artist)
                title = yt_title
                album = yt_album

            # Sanitize filesystem names
            safe_primary_artist = self.sanitize_filename(primary_artist)
            safe_album = self.sanitize_filename(album)
            safe_title = self.sanitize_filename(title)
            
            # Structure folder based on primary artist to avoid chaotic folders
            file_path = self.paths.get_permanente_track_path(safe_primary_artist, safe_album, safe_title)
            extracted.append({
                'id': vid,
                'title': title,
                'artist': full_artist, # Full artist list for Pano Scrobbler and tags
                'album': album,
                'duration_seconds': 0,
                'file_path': file_path
            })
            
            if idx % 200 == 0 or idx == total_tracks:
                print(f"[{idx}/{total_tracks}] Tracks prepared with clean metadata...")
                
        self._save_to_db(extracted)
        return "Permanent Collection", extracted

    def extract_playlist(self, playlist_id: str, resolve_albums: bool = True):
        """
        Extracts tracks from a YouTube Music playlist.
        If YouTube API cuts pagination with 403/Empty Response,
        falls back to local base_datos.json if available.
        """
        print(f"Fetching playlist information ({playlist_id}) from YouTube Music...")
        tracks = []
        playlist_title = f"Playlist_{playlist_id}"
        
        try:
            playlist = self.yt.get_playlist(playlist_id, limit=None)
            playlist_title = self.sanitize_filename(playlist.get('title', playlist_title))
            tracks = playlist.get('tracks', [])
        except Exception as e:
            print(f"\n[!] Warning: YouTube Music API severed continuous playlist fetch (+1000 songs): {e}")
            local_json = "../Herramientas/Sincronizador_YT/registros/base_datos.json"
            if os.path.exists(local_json):
                print(f"[*] Activating safe fallback: Detected your synchronized local file '{local_json}'.")
                print("[*] Importing directly the 993 songs without encountering YouTube API blocks...")
                return self.import_from_local_database(local_json)
            else:
                raise
            
        total_tracks = len(tracks)
        print(f"Playlist found: '{playlist_title}' with {total_tracks} songs.")
        print("Processing and prioritizing studio album versions...")
        
        extracted = []
        for idx, t in enumerate(tracks, start=1):
            vid = t.get('videoId')
            if not vid:
                continue
                
            title = t.get('title', 'Unknown Title')
            artists = [a['name'] for a in t.get('artists', []) if 'name' in a]
            artist = artists[0] if artists else "Unknown Artist"
            album = t.get('album', {}).get('name') if t.get('album') else None
            duration = t.get('duration_seconds', 0)
            
            if resolve_albums:
                resolved = resolve_album_track(self.yt, artist, title, current_vid=vid, current_album=album)
                final_vid = resolved['id'] or vid
                final_title = resolved['title']
                final_artist = resolved['artist']
                final_album = resolved['album']
                final_track_num = resolved.get('track_number') if resolve_albums else None
                final_rel_date = resolved.get('release_date') if resolve_albums else None
                final_duration = resolved['duration_seconds'] or duration
            else:
                final_vid = vid
                final_title = title
                final_artist = artist
                final_album = album or "Singles"
                final_track_num = None
                final_rel_date = None
                final_duration = duration
                
            file_path = self.paths.get_permanente_track_path(final_artist, final_album, final_title)
            
            extracted.append({
                'id': final_vid,
                'title': final_title,
                'artist': final_artist,
                'album': final_album,
                'duration_seconds': final_duration,
                'file_path': file_path,
                'track_number': final_track_num,
                'release_date': final_rel_date
            })
            
            if idx % 50 == 0 or idx == total_tracks:
                print(f"[{idx}/{total_tracks}] Tracks processed and assigned to Permanent...")
                
        self._save_to_db(extracted)
        return playlist_title, extracted
        
    def _save_to_db(self, tracks: list[dict]):
        """Inserts track metadata as PENDING in Permanent."""
        with get_db_connection(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            cursor = conn.cursor()
            for t in tracks:
                cursor.execute("""
                    INSERT OR REPLACE INTO tracks (id, title, artist, album, duration_seconds, status, is_permanent, file_path, track_number, release_date)
                    VALUES (?, ?, ?, ?, ?, 'PENDING', 1, ?, ?, ?)
                """, (t['id'], t['title'], t['artist'], t['album'], t['duration_seconds'], t['file_path'], t.get('track_number'), t.get('release_date')))
            conn.commit()

    def generate_taste_profile(self, profile_path: str = "data/taste_profile.json"):
        """Generates data/taste_profile.json based on permanent collection."""
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT artist FROM tracks WHERE is_permanent = 1")
            artists = [row[0] for row in cursor.fetchall()]
            
        total_tracks = len(artists)
        counter = Counter(artists)
        top_artists = dict(counter.most_common(50))
        
        profile = {
            "total_tracks": total_tracks,
            "top_artists": top_artists,
            "genre_seeds": []
        }
        
        os.makedirs(os.path.dirname(profile_path), exist_ok=True)
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)
            
        return profile
