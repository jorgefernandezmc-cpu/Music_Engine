import os
import json
import re
import sqlite3
from collections import Counter
from ytmusicapi import YTMusic

class YTMExtractor:
    def __init__(self, db_path: str, storage_base: str, auth_file: str = "config/headers_auth.json"):
        self.db_path = db_path
        self.storage_base = storage_base
        if os.path.exists(auth_file):
            self.yt = YTMusic(auth_file)
        else:
            self.yt = YTMusic()
            
    def sanitize_filename(self, name: str) -> str:
        """Sanitiza nombres de archivos para evitar caracteres prohibidos en sistemas de archivos."""
        if not name:
            return "Unknown"
        name = re.sub(r'[/\\:*?"<>|]', '-', name)
        return name.strip('. ')

    def extract_playlist(self, playlist_id: str):
        """Extrae la información de una playlist y la guarda en la base de datos."""
        playlist = self.yt.get_playlist(playlist_id, limit=None)
        playlist_title = self.sanitize_filename(playlist.get('title', f"Playlist_{playlist_id}"))
        playlist_dir = os.path.join(self.storage_base, playlist_title)
        
        # Ensure the playlist directory exists
        os.makedirs(playlist_dir, exist_ok=True)
        
        tracks = playlist.get('tracks', [])
        extracted = []
        
        for t in tracks:
            vid = t.get('videoId')
            if not vid:
                continue
            title = t.get('title', 'Unknown Title')
            artists = [a['name'] for a in t.get('artists', []) if 'name' in a]
            artist = artists[0] if artists else "Unknown Artist"
            album = t.get('album', {}).get('name') if t.get('album') else None
            duration = t.get('duration_seconds', 0)
            
            safe_title = self.sanitize_filename(title)
            safe_artist = self.sanitize_filename(artist)
            
            # Formato esperado: storage/Permanente/{Playlist_Sanitizada}/{Artista} - {Titulo}.opus
            file_path = f"{self.storage_base}/{playlist_title}/{safe_artist} - {safe_title}.opus"
            
            extracted.append({
                'id': vid,
                'title': title,
                'artist': artist,
                'album': album,
                'duration_seconds': duration,
                'file_path': file_path
            })
            
        self._save_to_db(extracted)
        return playlist_title, extracted
        
    def _save_to_db(self, tracks: list[dict]):
        """Inserta los metadatos de las pistas de manera transaccional."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            cursor = conn.cursor()
            for t in tracks:
                cursor.execute("""
                    INSERT OR REPLACE INTO tracks (id, title, artist, album, duration_seconds, status, is_permanent, file_path)
                    VALUES (?, ?, ?, ?, ?, 'PENDING', 1, ?)
                """, (t['id'], t['title'], t['artist'], t['album'], t['duration_seconds'], t['file_path']))
            conn.commit()

    def generate_taste_profile(self, profile_path: str = "data/taste_profile.json"):
        """Genera el data/taste_profile.json basado en la colección permanente."""
        with sqlite3.connect(self.db_path) as conn:
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
