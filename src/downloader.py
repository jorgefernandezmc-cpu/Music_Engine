import os
import sqlite3
import logging
import yaml
import yt_dlp
import base64
import urllib.request
import json
from mutagen.oggopus import OggOpus
from mutagen.flac import Picture
from mutagen.mp4 import MP4, MP4Cover

logger = logging.getLogger('downloader')
os.makedirs('logs', exist_ok=True)
if not logger.handlers:
    fh = logging.FileHandler('logs/downloader.log')
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(fh)
    logger.setLevel(logging.INFO)

class Downloader:
    def __init__(self, db_path: str, config_path: str = "config/config.yaml"):
        self.db_path = db_path
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
            
        self.dl_config = self.config.get('downloader', {})
        
    def download_pending_tracks(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, file_path, is_permanent, status FROM tracks WHERE status IN ('PENDING', 'PENDING_ANTOJO') LIMIT ?", (self.dl_config.get('batch_size', 50),))
            pending = cursor.fetchall()
            
            if not pending:
                return 0
                
            base_ydl_opts = {
                'format': 'bestaudio/best',
                'writethumbnail': True,
                'postprocessors': [
                    {'key': 'FFmpegExtractAudio', 'preferredcodec': self.dl_config.get('preferred_codec', 'opus')},
                    {'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'}
                ],
                'download_archive': 'data/download_archive.txt',
                'quiet': True,
                'no_warnings': True,
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'web']
                    }
                }
            }
            
            downloaded = 0
            
            for t_id, f_path, is_perm, current_status in pending:
                base_path = os.path.splitext(f_path)[0]
                
                download_success = False
                ydl_opts_current = base_ydl_opts.copy()
                ydl_opts_current['outtmpl'] = {'default': f"{base_path}.%(ext)s"}
                
                try:
                    with yt_dlp.YoutubeDL(ydl_opts_current) as ydl:
                        logger.info(f"Descargando {t_id} a {base_path}")
                        url = f"https://www.youtube.com/watch?v={t_id}"
                        error_code = ydl.download([url])
                        if error_code == 0:
                            download_success = True
                except Exception as e:
                    logger.error(f"Error descargando {t_id}: {e}")
                    
                if download_success:
                    new_status = 'PERMANENT' if is_perm else ('ANTOJO' if current_status == 'PENDING_ANTOJO' else 'CINTA')
                    actual_path = f_path
                    if not os.path.exists(actual_path) and os.path.exists(f"{base_path}.m4a"):
                        actual_path = f"{base_path}.m4a"
                        
                    # Aplicar siempre Mutagen tras descarga exitosa
                    try:
                        cursor.execute("SELECT title, artist, album, genre FROM tracks WHERE id = ?", (t_id,))
                        row = cursor.fetchone()
                        if row:
                            t_title, t_artist, t_album, t_genre = row
                            thumb_path = f"{base_path}.jpg"
                            
                            if actual_path.endswith('.opus'):
                                audio = OggOpus(actual_path)
                                audio["title"] = t_title
                                audio["artist"] = t_artist

                                if t_album:
                                    audio["album"] = t_album
                                if t_genre:
                                    audio["genre"] = t_genre
                                    
                                # Fetch Lyrics from LRCLIB
                                try:
                                    import urllib.parse
                                    query = urllib.parse.urlencode({'track_name': t_title, 'artist_name': t_artist})
                                    req = urllib.request.Request(f"https://lrclib.net/api/search?{query}", headers={'User-Agent': 'MusicConveyorBot/1.0'})
                                    with urllib.request.urlopen(req, timeout=5) as response:
                                        data = json.loads(response.read().decode('utf-8'))
                                        if data and len(data) > 0:
                                            synced = data[0].get('syncedLyrics')
                                            plain = data[0].get('plainLyrics')
                                            best_lyrics = synced if synced else plain
                                            if best_lyrics:
                                                audio["LYRICS"] = best_lyrics
                                                logger.info(f"Letra encontrada e incrustada para {t_title}")
                                except Exception as lrc_e:
                                    logger.warning(f"No se pudo obtener letra para {t_title}: {lrc_e}")
                                    
                                if os.path.exists(thumb_path):
                                    pic = Picture()
                                    with open(thumb_path, "rb") as p:
                                        pic.data = p.read()
                                    pic.type = 3
                                    pic.mime = u"image/jpeg"
                                    pic_data = pic.write()
                                    encoded_data = base64.b64encode(pic_data).decode("ascii")
                                    audio["metadata_block_picture"] = [encoded_data]
                                    
                                audio.save()
                                
                            elif actual_path.endswith('.m4a'):
                                audio = MP4(actual_path)
                                audio["\xa9nam"] = t_title
                                audio["\xa9ART"] = t_artist
                                if t_album:
                                    audio["\xa9alb"] = t_album
                                if t_genre:
                                    audio["\xa9gen"] = t_genre
                                    
                                if os.path.exists(thumb_path):
                                    with open(thumb_path, "rb") as p:
                                        audio["covr"] = [MP4Cover(p.read(), imageformat=MP4Cover.FORMAT_JPEG)]
                                        
                                audio.save()
                                
                            if os.path.exists(thumb_path):
                                os.remove(thumb_path)
                    except Exception as meta_e:
                        logger.error(f"Fallo aplicando metadatos con mutagen a {t_id}: {meta_e}")
                        
                    cursor.execute("""
                        UPDATE tracks 
                        SET status = ?, added_at = CURRENT_TIMESTAMP, file_path = ?
                        WHERE id = ?
                    """, (new_status, actual_path, t_id))
                    downloaded += 1
                else:
                    cursor.execute("UPDATE tracks SET status = 'FAILED' WHERE id = ?", (t_id,))
                        
            conn.commit()
            return downloaded
