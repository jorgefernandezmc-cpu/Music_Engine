"""
sync.py
Specialized module for physical synchronization of local files and change detection:
- sync_manual_moves: Detects manual file movements within Permanent.
- clean_ghost_tracks: Detects manual file deletions and purges orphan .lrc files.
- process_local_file_ratings: Evaluates local file rating tags (1 star = purge, 4-5 stars = permanent).
"""

import os
import shutil
import logging
import hashlib
import mutagen
from src.db import get_db_connection

logger = logging.getLogger('sync')

class FileSyncManager:
    def __init__(self, db_path: str, paths, playlist_generator, config: dict = None):
        self.db_path = db_path
        self.paths = paths
        self.playlists = playlist_generator
        self.config = config or {}
        
        storage_cfg = self.config.get('storage', {})
        self.mass_deletion_limit = storage_cfg.get('mass_deletion_failsafe_limit', 50)

    def sync_manual_moves(self) -> int:
        """
        Scans permanente_dir to find files manually moved
        into Permanent or between albums. If matches are found,
        updates the database marking them as PERMANENT.
        """
        permanente_dir = self.paths.permanente_dir
        if not os.path.exists(permanente_dir):
            return 0
            
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, file_path, status, album FROM tracks")
            all_tracks = cursor.fetchall()
            
            basename_map = {}
            for t_id, f_path, t_status, t_album in all_tracks:
                if f_path:
                    basename = os.path.basename(f_path)
                    basename_map[basename] = (t_id, f_path, t_status, t_album)
                    
            updated_count = 0
            for root, dirs, files in os.walk(permanente_dir):
                for file in files:
                    if not file.endswith(('.opus', '.m4a', '.mp3', '.flac')):
                        continue
                        
                    new_abs_path = os.path.abspath(os.path.join(root, file))
                    
                    if file in basename_map:
                        t_id, old_f_path, old_status, old_album = basename_map[file]
                        
                        # Detect if file changed location within Permanent
                        if old_f_path != new_abs_path:
                            parent_dir_name = os.path.basename(root)
                            new_album = parent_dir_name if parent_dir_name else old_album
                            
                            cursor.execute("""
                                UPDATE tracks 
                                SET status = 'PERMANENT', is_permanent = 1, file_path = ?, album = ?
                                WHERE id = ?
                            """, (new_abs_path, new_album, t_id))
                            updated_count += 1
                            logger.info(f"Manual move synced: {file} -> {new_abs_path} (Album: {new_album})")
                        elif old_status != 'PERMANENT':
                            cursor.execute("""
                                UPDATE tracks 
                                SET status = 'PERMANENT', is_permanent = 1, file_path = ?
                                WHERE id = ?
                            """, (new_abs_path, t_id))
                            updated_count += 1
                            logger.info(f"Move to Permanent synced: {file} -> PERMANENT")
                    else:
                        # New physical file in Permanent not yet recorded in DB
                        try:
                            audio = mutagen.File(new_abs_path)
                            art, tit = None, None
                            alb = os.path.basename(root)
                            dur = 0
                            if audio:
                                if 'artist' in audio and audio['artist']: 
                                    art = str(audio['artist'][0])
                                elif '\xa9ART' in audio and audio['\xa9ART']: 
                                    art = str(audio['\xa9ART'][0])
                                if 'title' in audio and audio['title']: 
                                    tit = str(audio['title'][0])
                                elif '\xa9nam' in audio and audio['\xa9nam']: 
                                    tit = str(audio['\xa9nam'][0])
                                if 'album' in audio and audio['album']: 
                                    alb = str(audio['album'][0])
                                elif '\xa9alb' in audio and audio['\xa9alb']: 
                                    alb = str(audio['\xa9alb'][0])
                                if getattr(audio, 'info', None) and getattr(audio.info, 'length', None):
                                    dur = int(round(audio.info.length))
                            if not tit or not art:
                                base_name = os.path.splitext(file)[0]
                                if ' - ' in base_name:
                                    parts = base_name.split(' - ', 1)
                                    art = art or parts[0].strip()
                                    tit = tit or parts[1].strip()
                                else:
                                    tit = tit or base_name
                                    art = art or os.path.basename(os.path.dirname(root))
                            synth_id = f"manual_{hashlib.md5(new_abs_path.encode()).hexdigest()[:11]}"
                            cursor.execute("""
                                INSERT OR REPLACE INTO tracks (id, title, artist, album, duration_seconds, status, is_permanent, file_path)
                                VALUES (?, ?, ?, ?, ?, 'PERMANENT', 1, ?)
                            """, (synth_id, tit, art, alb, dur, new_abs_path))
                            updated_count += 1
                            logger.info(f"New track in Permanent auto-indexed: {art} - {tit} ({new_abs_path})")
                        except Exception as e:
                            logger.warning(f"Error auto-indexing new file {new_abs_path}: {e}")
                            
            if updated_count > 0:
                conn.commit()
                logger.info(f"Reverse Sync: {updated_count} tracks synchronized to PERMANENT.")
                self.playlists.update_permanent_playlists()
                
            return updated_count

    def clean_ghost_tracks(self) -> int:
        """
        Scans DB for tracks whose physical files were deleted.
        Marks missing tracks as PURGED.
        Includes failsafe against mass accidental deletions.
        """
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, file_path FROM tracks WHERE status IN ('CINTA', 'PERMANENT', 'ANTOJO')")
            active_tracks = cursor.fetchall()
            
            missing_tracks = []
            for t_id, f_path in active_tracks:
                if f_path and not os.path.exists(f_path):
                    missing_tracks.append((t_id, f_path))
                    
            if len(missing_tracks) > self.mass_deletion_limit:
                logger.error(f"CRITICAL! Detected {len(missing_tracks)} deleted files at once (Safety limit: {self.mass_deletion_limit}).")
                logger.error("Aborting ghost cleanup to prevent accidental mass purge (potential Syncthing or SD card issue).")
                return 0
                
            ghost_count = 0
            for t_id, f_path in missing_tracks:
                new_status = 'PURGED'
                cursor.execute("UPDATE tracks SET status = ? WHERE id = ?", (new_status, t_id))
                ghost_count += 1
                logger.info(f"Ghost Cleaner: Deleted file detected. Status {new_status} for {t_id}")
                
                # If audio was deleted, delete corresponding .lrc sidecar file
                if f_path:
                    base_path = os.path.splitext(f_path)[0]
                    for ext in ('.lrc', '.jpg', '.png'):
                        sidecar = f"{base_path}{ext}"
                        if os.path.exists(sidecar):
                            try:
                                os.remove(sidecar)
                                logger.info(f"Ghost Cleaner: Removed auxiliary file: {sidecar}")
                            except Exception as e:
                                logger.warning(f"Error deleting auxiliary file {sidecar}: {e}")
                
            # Preventative cleanup of orphan .lrc files without corresponding audio
            for dirpath, _, filenames in os.walk(self.paths.base_dir):
                for f in filenames:
                    if f.endswith('.lrc'):
                        base = os.path.splitext(f)[0]
                        has_audio = any(
                            os.path.exists(os.path.join(dirpath, base + audio_ext))
                            for audio_ext in ('.opus', '.m4a', '.mp3', '.flac', '.ogg', '.wav')
                        )
                        if not has_audio:
                            orphan_file = os.path.join(dirpath, f)
                            try:
                                os.remove(orphan_file)
                                logger.info(f"Ghost Cleaner: Removed orphan .lrc: {orphan_file}")
                            except Exception as e:
                                logger.warning(f"Error deleting orphan .lrc {orphan_file}: {e}")
                
            if ghost_count > 0:
                conn.commit()
                logger.info(f"Ghost Cleaner: {ghost_count} tracks marked as PURGED.")
                self.playlists.update_all_playlists()
                
            return ghost_count

    def process_local_file_ratings(self) -> None:
        """
        Reads rating tags in local audio files (Vorbis RATING / ID3 POPM):
        - Rating 1: Purge track immediately.
        - Rating 4 or 5: Promote immediately to Permanent.
        """
        for dirpath, _, filenames in os.walk(self.paths.base_dir):
            for f in filenames:
                if not f.endswith(('.opus', '.mp3', '.flac', '.m4a')):
                    continue
                    
                filepath = os.path.join(dirpath, f)
                
                try:
                    audio = mutagen.File(filepath)
                    if not audio: 
                        continue
                    
                    rating = 0
                    
                    # Opus / FLAC (Vorbis comments)
                    if 'RATING' in audio:
                        try:
                            val = int(audio['RATING'][0])
                            rating = val if val <= 5 else int(val / 20)
                        except Exception: 
                            pass
                    
                    # MP3 (ID3 POPM)
                    elif hasattr(audio, 'tags') and audio.tags:
                        for tag in audio.tags.values():
                            if getattr(tag, 'FrameID', None) == 'POPM':
                                val = tag.rating
                                if val >= 196: rating = 5
                                elif val >= 128: rating = 4
                                elif val >= 64: rating = 3
                                elif val >= 1: rating = 1
                                break

                    if rating == 0:
                        continue

                    with get_db_connection(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT id, status, is_permanent, artist, album, title FROM tracks WHERE file_path = ?", (filepath,))
                        row = cursor.fetchone()
                        
                        if not row: 
                            continue
                        t_id, status, is_permanent, t_artist, t_album, t_title = row
                        
                        if rating == 1:
                            audio.delete()
                            try: os.remove(filepath)
                            except Exception: pass
                            lrc_p = os.path.splitext(filepath)[0] + ".lrc"
                            if os.path.exists(lrc_p):
                                try: os.remove(lrc_p)
                                except Exception: pass
                            new_status = 'PURGED'
                            cursor.execute("UPDATE tracks SET status = ?, file_path = NULL WHERE id = ?", (new_status, t_id))
                            logger.info(f"Rating 1: Purged {filepath} and associated lyrics.")
                            
                        elif rating in (4, 5):
                            new_path = self.paths.get_permanente_track_path(t_artist, t_album, t_title)
                            if filepath != new_path:
                                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                                if 'RATING' in audio: 
                                    del audio['RATING']
                                audio.save()
                                shutil.move(filepath, new_path)
                                cursor.execute("UPDATE tracks SET status = 'PERMANENT', is_permanent = 1, file_path = ? WHERE id = ?", (new_path, t_id))
                                logger.info(f"Rating {rating}: Moved to Permanent -> {new_path}")
                                
                except Exception as e:
                    logger.debug(f"Error processing rating for {filepath}: {e}")
                    continue
