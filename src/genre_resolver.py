"""
genre_resolver.py
Module for classification and exact assignment of musical genres in metadata and SQLite.

Strict retrieval hierarchy (Prioritizes free, open sources without AI):
1. Persistent cache in SQLite (artist_genres table) -> 0 requests, 0 cost, instantaneous.
2. MusicBrainz API (Open, community music catalog) -> 0 AI, filtered tags.
3. Deezer API (Free public catalog without API key) -> 0 AI, official album genres.
4. Gemini AI (Exceptional last resort) -> Only if open sources have no data.
5. Clean safe fallback -> If no source has data, defaults safely without hallucination.
"""

import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from mutagen.oggopus import OggOpus
from mutagen.mp4 import MP4
from src.db import get_db_connection

logger = logging.getLogger("genre_resolver")

# Canonical prioritized genre dictionary: specific subgenres precede generic terms
CANONICAL_GENRES = {
    # Urban / Latin Subgenres
    'trap latino': 'Trap Latino',
    'latin trap': 'Trap Latino',
    'reggaeton': 'Reggaeton',
    'regguetón': 'Reggaeton',
    'dembow': 'Dembow',
    'flamenco urbano': 'Flamenco Urbano',
    'trap': 'Trap',
    'drill': 'Drill',
    'latin rap': 'Rap',
    'latin urban': 'Urbano',
    'urbano latino': 'Urbano',
    'urbano': 'Urbano',
    'urban': 'Urbano',
    
    # Hip-Hop / Rap
    'boom bap': 'Hip-Hop',
    'hip hop': 'Hip-Hop',
    'hip-hop': 'Hip-Hop',
    'rap': 'Rap',
    'rap/hip hop': 'Hip-Hop / Rap',
    
    # Rock and Variants
    'hard rock': 'Hard Rock',
    'heavy metal': 'Metal',
    'metal': 'Metal',
    'punk rock': 'Punk',
    'punk': 'Punk',
    'indie rock': 'Indie Rock',
    'alternative rock': 'Rock Alternativo',
    'rock alternativo': 'Rock Alternativo',
    'rock urbano': 'Rock',
    'pop rock': 'Pop Rock',
    'pop-rock': 'Pop Rock',
    'rock': 'Rock',
    
    # Pop and Variants
    'indie pop': 'Indie Pop',
    'latin pop': 'Pop Latino',
    'pop latino': 'Pop Latino',
    'synthpop': 'Synthpop',
    'synth-pop': 'Synthpop',
    'dance-pop': 'Pop',
    'dream pop': 'Indie Pop',
    'pop': 'Pop',
    'indie': 'Indie',
    
    # Electronic
    'french house': 'House',
    'techno/house': 'House',
    'deep house': 'House',
    'house': 'House',
    'techno': 'Techno',
    'electro': 'Electrónica',
    'electronic': 'Electrónica',
    'electronica': 'Electrónica',
    'electrónica': 'Electrónica',
    'edm': 'Electrónica',
    'dance': 'Electrónica',
    
    # R&B / Soul
    'contemporary r&b': 'R&B',
    'r&b': 'R&B',
    'soul': 'Soul',
    
    # Traditional / Roots
    'rumba flamenca': 'Rumba',
    'flamenco rumba': 'Rumba',
    'flamenco': 'Flamenco',
    'rumba': 'Rumba',
    'bachata': 'Bachata',
    'salsa': 'Salsa'
}

# Priority weights to favor specific subgenres over broad tags
GENRE_PRIORITY = {
    'Reggaeton': 10,
    'Trap Latino': 10,
    'Dembow': 10,
    'Flamenco Urbano': 10,
    'Hard Rock': 10,
    'Synthpop': 10,
    'House': 10,
    'Techno': 10,
    'Flamenco': 10,
    'Rumba': 10,
    'Bachata': 10,
    'Salsa': 10,
    'Indie Rock': 8,
    'Indie Pop': 8,
    'Rock Alternativo': 8,
    'Pop Rock': 8,
    'Trap': 8,
    'Urbano': 7,
    'Metal': 7,
    'Punk': 7,
    'R&B': 7,
    'Hip-Hop / Rap': 6,
    'Hip-Hop': 5,
    'Rap': 5,
    'Pop Latino': 5,
    'Rock': 4,
    'Electrónica': 4,
    'Pop': 3
}

_gemini_client = None


def get_gemini_client():
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client
        
    load_dotenv("config/.env")
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key and "your_" not in api_key:
        try:
            from google import genai
            _gemini_client = genai.Client(api_key=api_key)
        except Exception as e:
            logger.warning(f"Could not initialize Gemini client: {e}")
    return _gemini_client

def init_genre_cache_db(db_path: str = "data/conveyor_state.sqlite"):
    """Creates persistent artist genre cache table to avoid repeated calls."""
    with get_db_connection(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS artist_genres (
                artist TEXT PRIMARY KEY,
                genre TEXT NOT NULL,
                source TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def clean_genre_string(genre_raw: str) -> str:
    """Normalizes and cleans genre string, eliminating duplicates and formatting nicely."""
    if not genre_raw:
        return "Urbano"
        
    parts = re.split(r'[/;,|]', genre_raw)
    cleaned = []
    seen = set()
    
    for p in parts:
        item = p.strip()
        if not item or item.lower() in ("variado", "varied", "unknown", "desconocido", "null", "none"):
            continue
        title_item = " ".join(word.capitalize() for word in item.split())
        if title_item.lower() not in seen:
            seen.add(title_item.lower())
            cleaned.append(title_item)
            
    if not cleaned:
        return "Urbano"
        
    return " / ".join(cleaned[:2])

def _fetch_musicbrainz_recording_genre(artist: str, title: str) -> Optional[str]:
    """
    PRIORITY 1A NO-AI (TRACK LEVEL): Queries MusicBrainz Recording API.
    Retrieves specific track tags if community tags exist.
    """
    if not artist or not title:
        return None
        
    clean_art = artist.split(",")[0].split("&")[0].split("feat.")[0].split("with")[0].strip()
    clean_tit = title.split("(")[0].split("[")[0].strip()
    try:
        q_rec = urllib.parse.quote(f'recording:\"{clean_tit}\" AND artist:\"{clean_art}\"')
        url = f'https://musicbrainz.org/ws/2/recording/?query={q_rec}&fmt=json&limit=1'
        req = urllib.request.Request(url, headers={'User-Agent': 'MusicConveyor/2.0 (music@engine.local)'})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            recs = data.get('recordings', [])
            if recs:
                raw_tags = [t.get('name', '').lower().strip() for t in recs[0].get('tags', [])]
                matched = []
                seen = set()
                for tag in raw_tags:
                    if tag in CANONICAL_GENRES:
                        g = CANONICAL_GENRES[tag]
                        if g not in seen:
                            seen.add(g)
                            matched.append(g)
                            
                if matched:
                    matched.sort(key=lambda g: GENRE_PRIORITY.get(g, 1), reverse=True)
                    result = " / ".join(matched[:2])
                    logger.info(f"[MusicBrainz Track] Genre found for '{clean_art} - {clean_tit}': {result}")
                    return result
    except Exception as e:
        logger.debug(f"MusicBrainz recording error for '{clean_art} - {clean_tit}': {e}")
        
    return None

def _fetch_musicbrainz_artist_genre(artist: str) -> Optional[str]:
    """
    PRIORITY 1B NO-AI (ARTIST LEVEL): Queries MusicBrainz Artist API.
    Extracts artist tags and matches against canonical dictionary.
    """
    if not artist:
        return None
        
    clean_art = artist.split(",")[0].split("&")[0].split("feat.")[0].split("with")[0].strip()
    try:
        url = f'https://musicbrainz.org/ws/2/artist/?query=artist:\"{urllib.parse.quote(clean_art)}\"&fmt=json&limit=1'
        req = urllib.request.Request(url, headers={'User-Agent': 'MusicConveyor/2.0 (music@engine.local)'})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data and data.get('artists'):
                raw_tags = [t.get('name', '').lower().strip() for t in data['artists'][0].get('tags', [])]
                
                matched = []
                seen = set()
                for tag in raw_tags:
                    if tag in CANONICAL_GENRES:
                        g = CANONICAL_GENRES[tag]
                        if g not in seen:
                            seen.add(g)
                            matched.append(g)
                            
                if matched:
                    matched.sort(key=lambda g: GENRE_PRIORITY.get(g, 1), reverse=True)
                    result = " / ".join(matched[:2])
                    logger.info(f"[MusicBrainz Artist] Genre found for '{clean_art}': {result}")
                    return result
    except Exception as e:
        logger.debug(f"MusicBrainz API error for '{clean_art}': {e}")
        
    return None

def _fetch_deezer_genre(artist: str, title: str = "") -> Optional[str]:
    """
    PRIORITY 2 NO-AI (ALBUM/TRACK LEVEL): Queries Deezer API.
    Retrieves official categorization from the album or single to which the song belongs.
    """
    if not artist:
        return None
        
    clean_art = artist.split(",")[0].split("&")[0].split("feat.")[0].strip()
    clean_tit = title.split("(")[0].split("[")[0].strip() if title else ""
    query_str = f"{clean_art} {clean_tit}".strip() if clean_tit else clean_art
    
    try:
        q = urllib.parse.quote(query_str)
        url = f"https://api.deezer.com/search?q={q}&limit=1"
        req = urllib.request.Request(url, headers={'User-Agent': 'MusicEngine/1.0'})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('data'):
                alb_id = data['data'][0]['album']['id']
                alb_url = f"https://api.deezer.com/album/{alb_id}"
                req_alb = urllib.request.Request(alb_url, headers={'User-Agent': 'MusicEngine/1.0'})
                with urllib.request.urlopen(req_alb, timeout=3.0) as r_alb:
                    alb_data = json.loads(r_alb.read().decode('utf-8'))
                    genres_data = alb_data.get('genres', {}).get('data', [])
                    matched = []
                    seen = set()
                    for g in genres_data:
                        name = g.get('name', '').lower().strip()
                        if name in CANONICAL_GENRES:
                            canon = CANONICAL_GENRES[name]
                            if canon not in seen:
                                seen.add(canon)
                                matched.append(canon)
                        elif name and name not in ('latino', 'pop/rock', 'variado', 'varied'):
                            title_g = " ".join(w.capitalize() for w in name.split())
                            if title_g not in seen:
                                seen.add(title_g)
                                matched.append(title_g)
                                
                    if matched:
                        matched.sort(key=lambda g: GENRE_PRIORITY.get(g, 1), reverse=True)
                        result = " / ".join(matched[:2])
                        logger.info(f"[Deezer Album] Genre found for '{clean_art} - {clean_tit}': {result}")
                        return result
    except Exception as e:
        logger.debug(f"Deezer API error for '{clean_art}': {e}")
        
    return None

def resolve_genre(artist: str, title: str, db_path: str = "data/conveyor_state.sqlite", allow_ai: bool = True) -> str:
    """
    Resolves the genre of a track respecting per-track/album diversity:
    1. MusicBrainz Recording (Specific track, No AI)
    2. Deezer Album/Single (Specific album/single, No AI)
    3. MusicBrainz Artist (Artist tags, No AI)
    4. SQLite Artist Cache (Fast local fallback for artist)
    5. Gemini AI (Specific track as exceptional last resort)
    6. Safe fallback ('Urbano' or generic)
    """
    primary_artist = artist.split(",")[0].split("&")[0].split("feat.")[0].strip()
    
    def score_genre(g_str: Optional[str]) -> int:
        if not g_str:
            return 0
        parts = [p.strip() for p in g_str.split('/') if p.strip()]
        return max([GENRE_PRIORITY.get(part, 1) for part in parts] or [0])

    candidates = []
    
    # 1. MusicBrainz at track level (0 AI, maximum individual specificity)
    mb_rec_genre = _fetch_musicbrainz_recording_genre(primary_artist, title)
    if mb_rec_genre:
        candidates.append((score_genre(mb_rec_genre) + 2, mb_rec_genre, "mb_recording"))

    # 2. Deezer at album/single level (0 AI)
    dz_genre = _fetch_deezer_genre(primary_artist, title)
    if dz_genre:
        candidates.append((score_genre(dz_genre), dz_genre, "deezer"))
        
    # 3. MusicBrainz at general artist level (0 AI)
    mb_art_genre = _fetch_musicbrainz_artist_genre(primary_artist)
    if mb_art_genre:
        _save_artist_genre_cache(db_path, primary_artist, mb_art_genre, "musicbrainz")
        candidates.append((score_genre(mb_art_genre), mb_art_genre, "mb_artist"))

    # If any open source yielded data, select highest specificity
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_genre = candidates[0][1]
        logger.info(f"[Open Source Winner] {artist} - {title} => {best_genre} ({candidates[0][2]})")
        return best_genre

    # 4. Artist fallback cache in SQLite (0 AI)
    try:
        init_genre_cache_db(db_path)
        with get_db_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT genre FROM artist_genres WHERE artist = ?", (primary_artist,))
            row = c.fetchone()
            if row and row[0] and row[0] not in ("Variado", "Varied", "None", "", "Urbano"):
                return row[0]
    except Exception:
        pass
        
    # 5. Gemini AI specific to the track (EXCEPTIONAL LAST RESORT)
    if allow_ai:
        client = get_gemini_client()
        if client:
            prompt = (
                f"Specify the standard music genre(s) for the song '{title}' by artist '{artist}'. "
                "Choose 1 to 2 exact and recognizable genres (e.g. 'Reggaeton / Trap Latino', 'Rock', "
                "'Pop', 'Indie Rock', 'Hip-Hop / Rap', 'Electronic / House', 'Flamenco / Rumba'). "
                "Reply strictly with the genres separated by ' / ' without explanation."
            )
            try:
                resp = client.models.generate_content(model="gemini-3.5-flash", contents=prompt)
                raw = resp.text.strip() if resp and resp.text else ""
                if raw:
                    ai_genre = clean_genre_string(raw)
                    logger.info(f"[Gemini AI] Genre for song '{artist} - {title}': {ai_genre}")
                    return ai_genre
            except Exception as e:
                logger.warning(f"Error in Gemini fallback for '{artist} - {title}': {e}")
                
    # 6. Safe clean fallback
    fallback = "Urbano"
    return fallback

def _save_artist_genre_cache(db_path: str, artist: str, genre: str, source: str):
    """Saves to local database cache so subsequent songs by artist avoid network roundtrips."""
    try:
        with get_db_connection(db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO artist_genres (artist, genre, source) VALUES (?, ?, ?)",
                (artist, genre, source)
            )
            conn.commit()
    except Exception:
        pass

def apply_genre_metadata(file_path: str, genre_str: str) -> bool:
    """Embeds genre tags into physical audio file (.opus or .m4a)."""
    if not file_path or not os.path.exists(file_path):
        return False
        
    genres_list = [g.strip() for g in genre_str.split("/") if g.strip()]
    if not genres_list:
        genres_list = [genre_str]
        
    try:
        if file_path.endswith('.opus'):
            audio = OggOpus(file_path)
            audio["genre"] = genres_list
            audio.save()
            return True
        elif file_path.endswith('.m4a'):
            audio = MP4(file_path)
            audio["\xa9gen"] = genre_str
            audio.save()
            return True
    except Exception as e:
        logger.warning(f"Error embedding genre into metadata for {file_path}: {e}")
        
    return False

def enrich_library_genres(db_path: str = "data/conveyor_state.sqlite", 
                          limit: int = 50, 
                          force_all: bool = False,
                          allow_ai: bool = True) -> Dict[str, int]:
    """
    Scans library of existing tracks, resolves genres prioritizing open sources without AI,
    and updates both database and physical audio files.
    """
    init_genre_cache_db(db_path)
    logger.info(f"Starting genre scan (limit={limit}, allow_ai={allow_ai}, force_all={force_all})...")
    
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        if force_all:
            cursor.execute("""
                SELECT id, artist, title, file_path 
                FROM tracks 
                WHERE file_path IS NOT NULL AND status IN ('PERMANENT', 'CINTA')
                ORDER BY added_at DESC
            """)
        else:
            cursor.execute("""
                SELECT id, artist, title, file_path 
                FROM tracks 
                WHERE file_path IS NOT NULL 
                  AND status IN ('PERMANENT', 'CINTA')
                  AND (genre IS NULL OR genre = '' OR genre = 'Variado' OR genre = 'Varied')
                ORDER BY added_at DESC
            """)
        candidates = cursor.fetchall()
        
    to_process = candidates[:limit] if limit > 0 else candidates
    if not to_process:
        logger.info("No tracks pending genre classification.")
        return {"processed": 0, "updated": 0, "open_source_hits": 0, "ai_hits": 0}
        
    stats = {"processed": len(to_process), "updated": 0, "open_source_hits": 0, "ai_hits": 0}
    
    for t_id, art, tit, f_path in to_process:
        genre = resolve_genre(art, tit, db_path=db_path, allow_ai=allow_ai)
        if genre and genre not in ("Variado", "Varied"):
            with get_db_connection(db_path) as conn:
                conn.execute("UPDATE tracks SET genre = ? WHERE id = ?", (genre, t_id))
                conn.commit()
            if f_path and os.path.exists(f_path):
                apply_genre_metadata(f_path, genre)
            stats["updated"] += 1
            logger.info(f"[GENRE ASSIGNED] {art} - {tit} => {genre}")
            
        time.sleep(0.3) # Courtesy delay for free APIs
        
    logger.info(f"Genre enrichment completed: {stats['updated']}/{stats['processed']} tracks updated.")
    return stats
