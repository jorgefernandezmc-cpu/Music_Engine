import os
import time
import logging
from typing import Tuple, Dict, Any, Optional
from mutagen.oggopus import OggOpus
from mutagen.mp4 import MP4

from src.lyrics_provider import get_lyrics, has_lrc_timestamps, send_grouped_lyrics_notification
from src.album_resolver import get_primary_artist
from src.db import get_db_connection

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('lyric_enricher')

def _log_synced_event(artist: str, title: str, is_synced: bool, source: str, upgrade: bool = False):
    """Saves historical log of added lyrics into logs/lyrics_synced.log."""
    os.makedirs('logs', exist_ok=True)
    mode = "TOP-TIER UPGRADE" if upgrade else "NEW VERIFIED LYRICS"
    sync_str = "Synced (LRC)" if is_synced else "Plain text"
    with open("logs/lyrics_synced.log", "a", encoding="utf-8") as f:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"[{timestamp}] [{mode}] {artist} - {title} | {sync_str} | Source: {source}\n")

def check_and_upgrade_track(t_id: str, title: str, artist: str, f_path: str, duration: Optional[int] = None) -> Tuple[bool, str]:
    """
    Evaluates if a track lacks lyrics or can be upgraded to synced lyrics.
    Only accepts 100% verified lyrics (0% false positives).
    Returns: (was_updated, message)
    """
    if not f_path or not os.path.exists(f_path):
        return False, "Audio file does not exist"
        
    base_path = os.path.splitext(f_path)[0]
    lrc_path = f"{base_path}.lrc"
    
    current_has_lrc = os.path.exists(lrc_path)
    current_synced = False
    
    if current_has_lrc:
        try:
            with open(lrc_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                current_synced = has_lrc_timestamps(content)
        except Exception:
            current_has_lrc = False
            
    # If it already has real-time synced lyrics, it is already at the maximum tier
    if current_has_lrc and current_synced:
        return False, "Already has top-tier synced lyrics"
        
    primary_artist = get_primary_artist(artist)
    new_lyrics, new_synced, source = get_lyrics(title, primary_artist, video_id=t_id, duration=duration)
    
    if not new_lyrics:
        return False, "No verified lyrics found across providers"
        
    # Case 1: Did not have lyrics -> Save discovered lyrics
    if not current_has_lrc:
        _save_lyrics_to_disk_and_tags(f_path, lrc_path, new_lyrics, new_synced)
        _log_synced_event(artist, title, new_synced, source, upgrade=False)
        sync_str = "Synced [LRC]" if new_synced else "Plain text"
        return True, f"New lyrics assigned from {source} ({sync_str})"
        
    # Case 2: Had plain lyrics and new lyrics are synced -> UPGRADE TO TOP TIER
    if not current_synced and new_synced:
        _save_lyrics_to_disk_and_tags(f_path, lrc_path, new_lyrics, new_synced)
        _log_synced_event(artist, title, True, source, upgrade=True)
        return True, f"Top-tier upgrade! Promoted to synced lyrics from {source}"
        
    return False, "Already had plain lyrics and no synced version exists yet in top sources"

def _save_lyrics_to_disk_and_tags(f_path: str, lrc_path: str, lyrics: str, is_synced: bool):
    """Writes .lrc sidecar file and embeds tags inside audio file."""
    # 1. Save .lrc sidecar file
    try:
        with open(lrc_path, "w", encoding="utf-8") as lf:
            lf.write(lyrics)
    except Exception as e:
        logger.warning(f"Error writing sidecar {lrc_path}: {e}")
        
    # 2. Embed into audio tags
    try:
        if f_path.endswith('.opus'):
            audio = OggOpus(f_path)
            audio["LYRICS"] = lyrics
            if is_synced:
                audio["SYNCEDLYRICS"] = lyrics
            else:
                audio["UNSYNCEDLYRICS"] = lyrics
            audio.save()
        elif f_path.endswith('.m4a'):
            audio = MP4(f_path)
            audio["\xa9lyr"] = lyrics
            audio.save()
    except Exception as e:
        logger.warning(f"Error embedding metadata in {f_path}: {e}")

def run_daily_lyrics_enrichment(db_path: str = "data/conveyor_state.sqlite", 
                                limit: int = 50, 
                                upgrade_unsynced: bool = True,
                                rescan_all: bool = False) -> Dict[str, Any]:
    """
    Scans library identifying tracks without lyrics or with plain lyrics,
    attempting to fetch top-tier versions in safe, verified batches.
    """
    logger.info(f"Starting lyrics maintenance scan (limit={limit}, upgrades={upgrade_unsynced})...")
    
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, artist, file_path, duration_seconds 
            FROM tracks 
            WHERE file_path IS NOT NULL AND status IN ('PERMANENT', 'CINTA')
            ORDER BY is_permanent DESC, added_at DESC
        """)
        tracks = cursor.fetchall()
        
    missing_candidates = []
    unsynced_candidates = []
    other_candidates = []
    
    for t_id, title, artist, f_path, dur in tracks:
        if not f_path or not os.path.exists(f_path):
            continue
            
        base_path = os.path.splitext(f_path)[0]
        lrc_path = f"{base_path}.lrc"
        
        if not os.path.exists(lrc_path):
            missing_candidates.append((t_id, title, artist, f_path, dur))
        else:
            try:
                with open(lrc_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(500)
                    if has_lrc_timestamps(content):
                        if rescan_all:
                            other_candidates.append((t_id, title, artist, f_path, dur))
                    else:
                        if upgrade_unsynced:
                            unsynced_candidates.append((t_id, title, artist, f_path, dur))
            except Exception:
                missing_candidates.append((t_id, title, artist, f_path, dur))
                
    # Priority: first tracks without lyrics, then tracks upgradable to synced
    all_queue = missing_candidates + unsynced_candidates + other_candidates
    to_process = all_queue[:limit] if limit > 0 else all_queue
    
    logger.info(f"Candidates found: {len(missing_candidates)} without lyrics, {len(unsynced_candidates)} unsynced. Processing {len(to_process)}...")
    
    stats = {"processed": 0, "new_lyrics": 0, "upgraded_to_synced": 0, "unchanged": 0}
    updated_items = []
    
    for t_id, title, artist, f_path, dur in to_process:
        stats["processed"] += 1
        was_updated, msg = check_and_upgrade_track(t_id, title, artist, f_path, duration=dur)
        
        if was_updated:
            is_synced = ("synced" in msg.lower()) or ("sincronizada" in msg.lower())
            if "Top-tier upgrade" in msg or "Actualizada a nivel superior" in msg:
                stats["upgraded_to_synced"] += 1
            else:
                stats["new_lyrics"] += 1
            updated_items.append({"artist": artist, "title": title, "is_synced": is_synced})
            logger.info(f"[{title} - {artist}]: {msg}")
        else:
            stats["unchanged"] += 1
            
        time.sleep(0.4) # Courtesy delay to avoid API rate limiting
        
    if updated_items:
        send_grouped_lyrics_notification(updated_items)
        
    logger.info(
        f"Lyrics maintenance completed. "
        f"Processed: {stats['processed']}, "
        f"New assigned: {stats['new_lyrics']}, "
        f"Upgraded to synced: {stats['upgraded_to_synced']}, "
        f"Unchanged: {stats['unchanged']}"
    )
    return stats

if __name__ == "__main__":
    run_daily_lyrics_enrichment(limit=50)
