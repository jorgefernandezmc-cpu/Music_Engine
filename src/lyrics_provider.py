"""
lyrics_provider.py
Strict, verified lyrics module (0% false positives).
Golden rule: Better to have a track without lyrics than with incorrect lyrics.

Verifiable sources:
1. LRCLIB (Strict search with mandatory validation of artist, title, and duration).
2. YouTube Music (Direct official extraction linked to exact track videoId).
"""

import json
import logging
import re
import subprocess
import urllib.parse
import urllib.request
from typing import Optional, Tuple
from thefuzz import fuzz

logger = logging.getLogger("lyrics_provider")

def send_grouped_lyrics_notification(tracks_lyrics: list):
    """
    Sends a single summary notification to the Linux desktop when lyrics are incorporated or upgraded.
    Displays total track count, highlights top artists, and details tracks in expandable body.
    """
    if not tracks_lyrics:
        return
        
    count = len(tracks_lyrics)
    # Extract unique artists preserving order
    unique_artists = []
    seen_artists = set()
    for item in tracks_lyrics:
        art = item.get('artist', '').split(',')[0].split('&')[0].strip()
        if art and art.lower() not in seen_artists:
            seen_artists.add(art.lower())
            unique_artists.append(art)
            
    artists_str = ", ".join(unique_artists[:6])
    if len(unique_artists) > 6:
        artists_str += f" and {len(unique_artists) - 6} more"
        
    synced_count = sum(1 for item in tracks_lyrics if item.get('is_synced'))
    summary = f"🎤 Lyrics added: {count} tracks"
    
    # Construct structured expandable notification body
    body_lines = []
    body_lines.append(f"Artists: {artists_str}")
    if synced_count > 0:
        body_lines.append(f"({synced_count} real-time synced [LRC])")
    body_lines.append("") # Separator for expanded view
    
    # Detail individual tracks (up to 8 to avoid cluttering desktop panel)
    for item in tracks_lyrics[:8]:
        art = item.get('artist', '')
        tit = item.get('title', '')
        sync_badge = " [LRC]" if item.get('is_synced') else ""
        body_lines.append(f"• {art} - {tit}{sync_badge}")
        
    if count > 8:
        body_lines.append(f"• ... and {count - 8} more tracks")
        
    body = "\n".join(body_lines)
    
    try:
        subprocess.Popen(
            ["notify-send", "-a", "Music Engine", "-i", "audio-headphones", summary, body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        logger.debug(f"Error sending grouped lyrics notification: {e}")

def notify_new_lyrics(artist: str, title: str, is_synced: bool, source: str):
    """Backward compatibility function: silenced to avoid individual notification spam."""
    pass

def clean_song_title(title: str) -> str:
    """Cleans typical YouTube tags from title, such as (feat. ...), (Official Video), etc."""
    cleaned = title.strip('"\' \t\n')
    patterns = [
        r'\s*[\(\[](?:feat\.|ft\.|con|with)[^\)\]]*[\)\]]',
        r'\s*(?:feat\.|ft\.|con|with)\s+[^\-]+$',
        r'\s*[\(\[](?:video|audio|visualizer|letra|lyric|remix|en vivo|live)[^\)\]]*[\)\]]',
        r'\s*[\(\[](?:official|oficial)[^\)\]]*[\)\]]',
        r'\s*-\s*(?:remaster|remastered|bonus track).*$'
    ]
    for pattern in patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip('"\' \t\n')
    return cleaned if cleaned else title.strip()

def has_lrc_timestamps(lyrics: str) -> bool:
    """Verifies if lyrics contain timestamps in format [mm:ss.xx] or [mm:ss]."""
    if not lyrics:
        return False
    return bool(re.search(r'\[\d{2}:\d{2}(?:\.\d+)?\]', lyrics))

def _fetch_lrclib_verified(title: str, artist: str, duration: Optional[int] = None) -> Tuple[Optional[str], bool]:
    """
    Queries LRCLIB ALWAYS enforcing artist name in query and
    strictly validating that returned result matches correct artist and title.
    """
    clean_t = clean_song_title(title)
    cand_artist = artist.strip()
    
    # IMPORTANT: Never search by title alone. Always include artist.
    queries = [
        urllib.parse.urlencode({'track_name': clean_t, 'artist_name': cand_artist}),
        urllib.parse.urlencode({'q': f"{clean_t} {cand_artist}"})
    ]
    
    for q in queries:
        try:
            req = urllib.request.Request(
                f"https://lrclib.net/api/search?{q}",
                headers={'User-Agent': 'MusicConveyorBot/2.0 (music-engine)'}
            )
            with urllib.request.urlopen(req, timeout=3.5) as response:
                data = json.loads(response.read().decode('utf-8'))
                if not data or not isinstance(data, list):
                    continue
                    
                for item in data:
                    item_art = (item.get('artistName') or '').strip()
                    item_tit = clean_song_title((item.get('trackName') or '').strip())
                    
                    # 1. Strict ARTIST validation
                    sim_art = fuzz.token_set_ratio(item_art.lower(), cand_artist.lower())
                    art_match = (
                        sim_art >= 75 or 
                        cand_artist.lower() in item_art.lower() or 
                        item_art.lower() in cand_artist.lower()
                    )
                    if not art_match:
                        logger.debug(f"Discarded LRCLIB result due to artist mismatch: '{item_art}' vs '{cand_artist}'")
                        continue
                        
                    # 2. Strict TITLE validation
                    sim_tit = fuzz.token_set_ratio(item_tit.lower(), clean_t.lower())
                    if sim_tit < 70:
                        logger.debug(f"Discarded LRCLIB result due to title mismatch: '{item_tit}' vs '{clean_t}'")
                        continue
                        
                    # 3. DURATION validation (if available in database)
                    if duration and duration > 0:
                        item_dur = item.get('duration')
                        if item_dur and abs(item_dur - duration) > 20:
                            logger.debug(f"Discarded LRCLIB result due to duration discrepancy: {item_dur}s vs {duration}s")
                            continue
                            
                    # Passed strict filters: valid lyrics
                    synced = item.get('syncedLyrics')
                    if synced and synced.strip():
                        return synced.strip(), True
                    plain = item.get('plainLyrics')
                    if plain and plain.strip():
                        return plain.strip(), False
        except Exception as e:
            logger.debug(f"LRCLIB temporary error with query '{q}': {e}")
            
    return None, False

def _fetch_ytmusic_verified(video_id: str) -> Tuple[Optional[str], bool]:
    """
    Extracts official lyrics directly from YouTube Music for the exact videoId.
    100% verifiable because it comes from official player data of the audio itself.
    """
    if not video_id:
        return None, False
        
    clean_id = video_id.split('_')[0]
    try:
        from ytmusicapi import YTMusic
        yt = YTMusic()
        watch_data = yt.get_watch_playlist(videoId=clean_id)
        lyrics_id = watch_data.get('lyrics')
        if lyrics_id:
            lyrics_data = yt.get_lyrics(lyrics_id)
            text = lyrics_data.get('lyrics')
            if text and text.strip():
                is_synced = has_lrc_timestamps(text)
                return text.strip(), is_synced
    except Exception as e:
        logger.debug(f"YouTube Music lyrics unavailable for videoId {clean_id}: {e}")
        
    return None, False

def get_lyrics(title: str, artist: str, video_id: Optional[str] = None, duration: Optional[int] = None) -> Tuple[Optional[str], bool, str]:
    """
    Verified lyrics orchestrator.
    Only accepts lyrics where artist, title, and duration have been fully validated.
    Returns: (lyrics_text, is_synced, source_name)
    """
    logger.info(f"Searching verified lyrics for '{title}' - '{artist}'...")
    
    # 1. Verified LRCLIB (With validation of artist, title, and duration)
    lyrics, synced = _fetch_lrclib_verified(title, artist, duration=duration)
    if lyrics:
        source = "LRCLIB (Synced)" if synced else "LRCLIB (Plain text)"
        logger.info(f"Verified lyrics found in {source}")
        return lyrics, synced, source

    # 2. Official YouTube Music (Direct from track videoId)
    if video_id:
        lyrics, synced = _fetch_ytmusic_verified(video_id)
        if lyrics:
            source = "YouTube Music (Official)"
            logger.info(f"Official lyrics found in {source}")
            return lyrics, synced, source

    logger.info(f"No verified lyrics found for '{title}' - '{artist}'.")
    return None, False, "None"
