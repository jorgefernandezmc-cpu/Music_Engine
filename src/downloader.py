import os
import sqlite3
import logging
import yaml
import yt_dlp
import base64
import urllib.request
import json
import time
import random
from mutagen.oggopus import OggOpus
from mutagen.flac import Picture
from mutagen.mp4 import MP4, MP4Cover

from src.paths import StoragePaths
from src.album_resolver import get_primary_artist
from src.lyrics_provider import get_lyrics, send_grouped_lyrics_notification
from src.genre_resolver import resolve_genre
from src.db import get_db_connection
from src.audio_processor import calculate_and_apply_gain, calculate_r128_gain, apply_replaygain_tags, normalize_library_audio


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
        self.config_path = config_path
        self.paths = StoragePaths(config_path)
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
            
        self.dl_config = self.config.get('downloader', {})
        
    def download_pending_tracks(self, retry_failed: bool = False):
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            status_filter = "('PENDING', 'FAILED')" if retry_failed else "('PENDING',)"
            cursor.execute(f"""
                SELECT id, file_path, is_permanent, status, title, artist, album, genre, duration_seconds, track_number, release_date 
                FROM tracks 
                WHERE status IN {status_filter} 
                LIMIT ?
            """, (self.dl_config.get('batch_size', 50),))
            pending = cursor.fetchall()
            
            if not pending:
                return 0
                
            base_ydl_opts = {
                'format': self.dl_config.get('audio_format', 'bestaudio/best'),
                'writethumbnail': True,
                'postprocessors': [
                    {'key': 'FFmpegExtractAudio', 'preferredcodec': self.dl_config.get('preferred_codec', 'opus')},
                    {'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'}
                ],
                'download_archive': 'data/download_archive.txt',
                'quiet': True,
                'no_warnings': True
            }
            
            # Automatic authentication: priority to cookies.txt or auto-extraction from browser
            cookies_file = "config/cookies.txt"
            if os.path.exists(cookies_file):
                base_ydl_opts['cookiefile'] = cookies_file
            elif self.dl_config.get('cookies_browser') or self.dl_config.get('cookiesfrombrowser'):
                browser_name = self.dl_config.get('cookies_browser') or self.dl_config.get('cookiesfrombrowser')
                base_ydl_opts['cookiesfrombrowser'] = (browser_name,)
            else:
                # Intelligent default detection of Brave on Linux
                brave_dir = os.path.expanduser("~/.config/BraveSoftware/Brave-Browser")
                if os.path.exists(brave_dir):
                    base_ydl_opts['cookiesfrombrowser'] = ('brave',)
            
            downloaded = 0
            lyrics_added = []
            
            for t_id, f_path, is_perm, current_status, t_title, t_artist, t_album, t_genre, t_dur, t_track_num, t_rel_date in pending:
                base_path = os.path.splitext(f_path)[0]
                os.makedirs(os.path.dirname(f_path), exist_ok=True)
                
                download_success = False
                ydl_opts_current = base_ydl_opts.copy()
                ydl_opts_current['outtmpl'] = {'default': f"{base_path}.%(ext)s"}
                
                # Progressive multi-level retry strategy against rate-limits (HTTP 403) or unavailable formats:
                # Level 1: Standard configuration
                # Level 2: Clean mode without browser cookies after pause (in case session expired)
                # Level 3: Alternative 'android,web' client after pause (bypasses 403 and YouTube web blocks)
                attempts = [ydl_opts_current]
                clean_opts = {k: v for k, v in ydl_opts_current.items() if k not in ('cookiesfrombrowser', 'cookiefile')}
                attempts.append(clean_opts)
                android_opts = clean_opts.copy()
                android_opts['extractor_args'] = {'youtube': {'player_client': ['android', 'web', 'mweb']}}
                attempts.append(android_opts)
                
                for attempt_idx, current_attempt_opts in enumerate(attempts):
                    try:
                        if attempt_idx > 0:
                            time.sleep(2 * attempt_idx)
                            logger.info(f"Retrying {t_id} (fallback strategy {attempt_idx+1})")
                        else:
                            logger.info(f"Downloading {t_id} to {base_path}")
                            
                        url = f"https://www.youtube.com/watch?v={t_id}"
                        with yt_dlp.YoutubeDL(current_attempt_opts) as ydl:
                            error_code = ydl.download([url])
                            if error_code == 0:
                                download_success = True
                                break
                    except Exception as e:
                        logger.warning(f"Attempt {attempt_idx+1} for {t_id} failed: {e}")
                    
                if download_success:
                    if is_perm:
                        new_status = 'PERMANENT'
                    elif getattr(self.paths, 'cravings_dir', None) and (self.paths.cravings_dir in f_path):
                        new_status = 'ANTOJO'
                    else:
                        new_status = 'CINTA'
                    actual_path = f_path
                    fallback_codec = self.dl_config.get('fallback_codec', 'm4a').lstrip('.')
                    fallback_file = f"{base_path}.{fallback_codec}"
                    if not os.path.exists(actual_path) and os.path.exists(fallback_file):
                        actual_path = fallback_file
                        
                    # Apply Mutagen tags upon successful download
                    try:
                        thumb_path = f"{base_path}.jpg"
                        p_artist = get_primary_artist(t_artist)
                        
                        # Verified lyrics retrieval (strict LRCLIB -> official YTMusic)
                        best_lyrics, is_synced, l_source = get_lyrics(t_title, p_artist, video_id=t_id, duration=t_dur)
                        if best_lyrics:
                            lyrics_added.append({"artist": t_artist, "title": t_title, "is_synced": is_synced})

                        # Exact genre retrieval and verification
                        if not t_genre or t_genre.strip() in ("", "Variado", "Varied", "None", "NULL"):
                            t_genre = resolve_genre(p_artist, t_title)
                            if t_genre and t_genre not in ("Variado", "Varied"):
                                cursor.execute("UPDATE tracks SET genre = ? WHERE id = ?", (t_genre, t_id))
                        
                        if actual_path.endswith('.opus'):
                            audio = OggOpus(actual_path)
                            audio["title"] = t_title
                            audio["artist"] = t_artist # Full collaborating artists for Pano Scrobbler and Lune
                            audio["albumartist"] = p_artist # Primary artist for clean navigation

                            if t_album:
                                audio["album"] = t_album
                            if t_genre:
                                genres_list = [g.strip() for g in t_genre.split("/") if g.strip()]
                                audio["genre"] = genres_list
                            if t_track_num:
                                audio["tracknumber"] = str(t_track_num)
                            if t_rel_date:
                                date_clean = str(t_rel_date).strip()
                                audio["date"] = date_clean
                                audio["year"] = date_clean[:4]

                            if best_lyrics:
                                audio["LYRICS"] = best_lyrics
                                if is_synced:
                                    audio["SYNCEDLYRICS"] = best_lyrics
                                else:
                                    audio["UNSYNCEDLYRICS"] = best_lyrics
                                    
                                # Generate .lrc sidecar file for universal compatibility (Lune, Retro Music, Auxio)
                                try:
                                    with open(f"{base_path}.lrc", "w", encoding="utf-8") as lf:
                                        lf.write(best_lyrics)
                                except Exception as lf_err:
                                    logger.warning(f"Could not write .lrc file: {lf_err}")
                                
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
                            audio["aART"] = p_artist
                            if t_album:
                                audio["\xa9alb"] = t_album
                            if t_genre:
                                audio["\xa9gen"] = t_genre
                            if t_track_num:
                                audio["trkn"] = [(int(t_track_num), 0)]
                            if t_rel_date:
                                audio["\xa9day"] = str(t_rel_date).strip()
                            if best_lyrics:
                                audio["\xa9lyr"] = best_lyrics
                                try:
                                    with open(f"{base_path}.lrc", "w", encoding="utf-8") as lf:
                                        lf.write(best_lyrics)
                                except Exception:
                                    pass
                                
                            if os.path.exists(thumb_path):
                                with open(thumb_path, "rb") as p:
                                    audio["covr"] = [MP4Cover(p.read(), imageformat=MP4Cover.FORMAT_JPEG)]
                                    
                            audio.save()
                            
                        if os.path.exists(thumb_path):
                            os.remove(thumb_path)

                        # Apply non-destructive ReplayGain / EBU R128 loudness tags
                        if self.dl_config.get('apply_replaygain', True):
                            target_lufs = float(self.dl_config.get('target_lufs', -18.0))
                            calculate_and_apply_gain(actual_path, target_lufs=target_lufs)
                    except Exception as meta_e:

                        logger.error(f"Failed applying metadata with mutagen to {t_id}: {meta_e}")
                        
                    cursor.execute("""
                        UPDATE tracks 
                        SET status = ?, added_at = CURRENT_TIMESTAMP, file_path = ?
                        WHERE id = ?
                    """, (new_status, actual_path, t_id))
                    downloaded += 1
                    sleep_min = float(self.dl_config.get('sleep_interval_min', 3))
                    sleep_max = float(self.dl_config.get('sleep_interval_max', 8))
                    if sleep_max > 0 and len(pending) > 1 and downloaded < len(pending):
                        sleep_s = random.uniform(sleep_min, sleep_max)
                        logger.debug(f"Pacing downloads: sleeping {sleep_s:.2f}s")
                        time.sleep(sleep_s)
                else:
                    cursor.execute("UPDATE tracks SET status = 'FAILED' WHERE id = ?", (t_id,))
                        
            conn.commit()
            if lyrics_added:
                send_grouped_lyrics_notification(lyrics_added)
            return downloaded
