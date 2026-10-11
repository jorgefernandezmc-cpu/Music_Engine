import logging
import time
import re
from thefuzz import fuzz

logger = logging.getLogger('album_resolver')

FORBIDDEN_WORDS = [
    "arcade", "cover", "8 bit", "8-bit", "speed up", "karaoke", "instrumental",
    "slowed", "type beat", "live", "directo", "sweet little band", "party tyme",
    "backing business", "tribute", "parody", "remake"
]

def is_suspicious_match(query_artist: str, query_title: str, yt_artist: str, yt_title: str) -> bool:
    """
    Detects whether a matched track is suspicious (e.g. cover, karaoke, 8-bit,
    or coming from an unrelated third-party channel).
    """
    combined_yt = f"{yt_title} {yt_artist}".lower()
    
    # 1. Forbidden keywords check
    for fw in FORBIDDEN_WORDS:
        if fw in combined_yt and fw not in query_title.lower():
            return True
            
    # 2. Primary artist similarity check
    prim_query = get_primary_artist(query_artist).lower()
    prim_yt = get_primary_artist(yt_artist).lower()
    
    sim_artist = fuzz.token_set_ratio(prim_query, prim_yt)
    if sim_artist < 45 and prim_query not in yt_artist.lower():
        return True
        
    return False

def is_studio_album(album_name: str, song_title: str) -> bool:
    """
    Determines if an album is a full studio album rather than a standalone single.
    """
    if not album_name:
        return False
    a_norm = album_name.lower().strip()
    t_norm = song_title.lower().strip()
    
    # If the album name exactly matches the song title, it is typically a single release
    if a_norm == t_norm:
        return False
        
    single_indicators = [
        '- single', '(single)', ' single', 'single ',
        'sencillo', '- ep', '(ep)', ' ep', 'ep ', 'remix pack'
    ]
    for ind in single_indicators:
        if ind in a_norm:
            return False
            
    return True

def get_primary_artist(artist_str: str) -> str:
    """
    Extracts the primary artist from a multi-artist string
    (e.g.: 'Anther, Dib' -> 'Anther', '3AM feat. Khea' -> '3AM').
    """
    if not artist_str:
        return 'Unknown Artist'
    # Split by commas, semicolons, or common collaboration keywords
    prim = re.split(r'[,;/]|\b(?:feat|ft|con|with)\b', artist_str, flags=re.IGNORECASE)[0].strip()
    return prim if prim else artist_str.strip()

def resolve_album_metadata(yt, album_browse_id: str, max_retries: int = 2) -> dict:
    """
    Fetches full metadata for an album (tracks with track number and release year).
    """
    if not album_browse_id:
        return {}
    for attempt in range(max_retries):
        try:
            return yt.get_album(album_browse_id)
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))
            else:
                logger.debug(f"Error fetching album {album_browse_id}: {e}")
    return {}

def resolve_song_release_date(yt, video_id: str, max_retries: int = 2) -> str:
    """
    Extracts publication date (YYYY-MM-DD or YYYY) using get_song microformat data.
    """
    if not video_id:
        return ""
    clean_id = video_id.split('_')[0] if '_' in video_id else video_id
    for attempt in range(max_retries):
        try:
            s_data = yt.get_song(clean_id)
            micro = s_data.get('microformat', {}).get('microformatDataRenderer', {})
            dt_str = micro.get('publishDate') or micro.get('uploadDate')
            if dt_str:
                return dt_str.split('T')[0]
            break
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))
    return ""

def resolve_album_track(yt, artist: str, title: str, current_vid: str = None, current_album: str = None, max_retries: int = 2) -> dict:
    """
    Checks if a song originates from an artist studio album on YouTube Music.
    If a high-fidelity studio album version exists, prioritizes it over a single
    or individual music video version.
    
    Returns a dictionary with:
    - id: videoId of selected version
    - title: normalized title
    - artist: normalized full collaborating artists
    - primary_artist: primary artist for directory structuring
    - album: album name (or 'Singles' if not from an album)
    - duration_seconds: duration
    - is_album_version: bool indicating if it belongs to a studio album
    - track_number: official album track number (int or None)
    - release_date: release date or year (YYYY-MM-DD or YYYY)
    """
    primary_artist = get_primary_artist(artist)
    # If a valid studio album and videoId are already available, attempt to retrieve track and date
    if current_album and is_studio_album(current_album, title) and current_vid:
        return {
            'id': current_vid,
            'title': title,
            'artist': artist,
            'primary_artist': primary_artist,
            'album': current_album,
            'duration_seconds': 0,
            'is_album_version': True,
            'track_number': None,
            'release_date': None
        }
        
    query = f"{artist} {title}".strip()
    results = []
    
    for attempt in range(max_retries):
        try:
            results = yt.search(query, filter="songs", limit=10)
            if not results and primary_artist and primary_artist != artist:
                results = yt.search(f"{primary_artist} {title}".strip(), filter="songs", limit=10)
            break
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(0.6 * (attempt + 1))
            else:
                logger.warning(f"Could not query YT Music to resolve album for '{query}': {e}")
                
    if not results:
        # Fallback to received original
        fallback_album = current_album if current_album else "Singles"
        return {
            'id': current_vid or '',
            'title': title,
            'artist': artist,
            'primary_artist': primary_artist,
            'album': fallback_album,
            'duration_seconds': 0,
            'is_album_version': is_studio_album(fallback_album, title),
            'track_number': None,
            'release_date': None
        }
        
    best_candidate = None
    best_score = -1
    best_album_id = None
    
    for r in results:
        r_vid = r.get('videoId')
        if not r_vid:
            continue
            
        r_title = r.get('title', '')
        r_artists = [a['name'] for a in r.get('artists', []) if 'name' in a]
        r_artist = r_artists[0] if r_artists else ''
        r_album_dict = r.get('album')
        r_album = r_album_dict.get('name') if r_album_dict else None
        r_album_id = r_album_dict.get('id') if r_album_dict else None
        r_duration = r.get('duration_seconds', 0)
        
        sim_title = fuzz.token_set_ratio(title.lower(), r_title.lower())
        sim_title_exact = fuzz.ratio(title.lower(), r_title.lower())
        sim_artist = fuzz.token_set_ratio(artist.lower(), r_artist.lower())
        sim_primary = fuzz.token_set_ratio(primary_artist.lower(), r_artist.lower())
        best_sim_artist = max(sim_artist, sim_primary)
        
        # Basic similarity filter to avoid picking another song
        if sim_title < 75 or (best_sim_artist < 60 and primary_artist.lower() not in r_artist.lower()):
            continue
            
        # Check distinctive keyword conflicts (e.g. "first" != "last", "remix", "pt 2")
        KEY_WORDS_DISTINCT = {
            'primer', 'primera', 'segundo', 'segunda', 'tercer', 'tercera',
            'ultimo', 'ultima', 'remix', 'intro', 'outro', 'parte', 'part',
            'first', 'second', 'third', 'last'
        }
        t_words = set(re.findall(r'\b\w+\b', title.lower()))
        cand_words = set(re.findall(r'\b\w+\b', r_title.lower()))
        has_conflict = any((kw in t_words and kw not in cand_words) or (kw in cand_words and kw not in t_words) for kw in KEY_WORDS_DISTINCT)
        if has_conflict:
            continue
            
        # Strict safety filter against covers, karaoke, 8-bit, and non-official channels
        if is_suspicious_match(artist, title, r_artist, r_title):
            continue
            
        score = sim_title + best_sim_artist
        is_album = is_studio_album(r_album, r_title) if r_album else False
        
        # Only apply album bonus if title matches with high fidelity (prevents album hijacking another song)
        if is_album and sim_title_exact >= 80:
            score += 100
            if 'deluxe' in r_album.lower() or 'edición' in r_album.lower() or 'edition' in r_album.lower():
                score += 5
        elif r_album:
            score += 10 # Has album/single instead of missing metadata
            
        if score > best_score:
            best_score = score
            best_album_id = r_album_id
            best_candidate = {
                'id': r_vid,
                'title': title if title else r_title,
                'artist': artist if artist else r_artist,
                'primary_artist': primary_artist,
                'album': r_album if r_album else (current_album or "Singles"),
                'duration_seconds': r_duration,
                'is_album_version': is_album,
                'track_number': None,
                'release_date': None
            }
            
    if best_candidate and best_score >= 150:
        # Enrich with track_number and album release date if available
        if best_album_id:
            alb_data = resolve_album_metadata(yt, best_album_id)
            if alb_data:
                alb_year = alb_data.get('year')
                if alb_year:
                    best_candidate['release_date'] = str(alb_year)
                for idx, t in enumerate(alb_data.get('tracks', []), 1):
                    t_vid = t.get('videoId')
                    t_tit = t.get('title', '')
                    if (t_vid and t_vid == best_candidate['id']) or fuzz.ratio(best_candidate['title'].lower(), t_tit.lower()) >= 85:
                        t_num = t.get('trackNumber')
                        best_candidate['track_number'] = int(t_num) if t_num else idx
                        break
        if not best_candidate.get('release_date'):
            s_date = resolve_song_release_date(yt, best_candidate['id'])
            if s_date:
                best_candidate['release_date'] = s_date

        if best_candidate['is_album_version']:
            logger.info(f"Prioritized album for '{artist} - {title}': Album '{best_candidate['album']}' [Track: {best_candidate.get('track_number')}, Date: {best_candidate.get('release_date')}] [ID: {best_candidate['id']}]")
        return best_candidate
        
    # Fallback if no candidate exceeded the threshold
    fb_vid = current_vid or (results[0].get('videoId') if results else '')
    fb_date = resolve_song_release_date(yt, fb_vid) if fb_vid else None
    return {
        'id': fb_vid,
        'title': title,
        'artist': artist,
        'primary_artist': primary_artist,
        'album': current_album or "Singles",
        'duration_seconds': 0,
        'is_album_version': False,
        'track_number': None,
        'release_date': fb_date
    }

def auto_fix_track(yt, artist: str, title: str, current_vid: str = None, client = None, model_name: str = "gemini-3.5-flash") -> dict:
    """
    Intelligent auto-repair algorithm for mismatched or questionable tracks:
    Level 1 (Strict Heuristic, No AI): Searches YT Music using only cleaned primary artist and filters forbidden words.
    Level 2 (Official Video Search, No AI): Searches for official music video version.
    Level 3 (Last Resort with AI): If both above fail or no reliable match is found,
            queries Gemini only for exact search terms in YouTube Music.
    """
    primary = get_primary_artist(artist)
    
    # --- LEVEL 1: Strict song search (No AI) ---
    queries = [
        f"{primary} {title}",
        f"{artist} {title}"
    ]
    
    for q in queries:
        try:
            results = yt.search(q, filter="songs", limit=10)
            for r in results:
                r_vid = r.get('videoId')
                if not r_vid:
                    continue
                r_title = r.get('title', '')
                r_artists = [a['name'] for a in r.get('artists', []) if 'name' in a]
                r_artist = r_artists[0] if r_artists else ''
                r_album = r.get('album', {}).get('name') if r.get('album') else None
                
                # Discard if cover, karaoke, 8-bit, etc.
                if is_suspicious_match(primary, title, r_artist, r_title):
                    continue
                    
                sim_title = fuzz.token_set_ratio(title.lower(), r_title.lower())
                sim_artist = fuzz.token_set_ratio(primary.lower(), r_artist.lower())
                
                if sim_title >= 75 and (sim_artist >= 60 or primary.lower() in r_artist.lower()):
                    logger.info(f"Auto-Fix (Heuristic) resolved '{artist} - {title}' -> '{r_artist} - {r_title}' [ID: {r_vid}]")
                    return {
                        'id': r_vid,
                        'title': title,
                        'artist': artist,
                        'primary_artist': primary,
                        'album': r_album or "Singles",
                        'fixed': True,
                        'method': 'heuristic'
                    }
        except Exception as e:
            logger.warning(f"Error in Auto-Fix level 1 for '{q}': {e}")
            
    # --- LEVEL 2: Official Video Search (No AI) ---
    try:
        vid_results = yt.search(f"{primary} {title} official video", filter="videos", limit=5)
        for r in vid_results:
            r_vid = r.get('videoId')
            r_title = r.get('title', '')
            r_artist = r.get('artists', [{}])[0].get('name', '') if r.get('artists') else ''
            
            if is_suspicious_match(primary, title, r_artist, r_title):
                continue
                
            sim_title = fuzz.token_set_ratio(title.lower(), r_title.lower())
            if sim_title >= 70:
                logger.info(f"Auto-Fix (Official Video) resolved '{artist} - {title}' [ID: {r_vid}]")
                return {
                    'id': r_vid,
                    'title': title,
                    'artist': artist,
                    'primary_artist': primary,
                    'album': "Singles",
                    'fixed': True,
                    'method': 'video_fallback'
                }
    except Exception as e:
        logger.warning(f"Error in Auto-Fix level 2 for '{primary} {title}': {e}")
        
    # --- LEVEL 3: AI as LAST RESORT ---
    if client:
        try:
            logger.info(f"Querying AI (Last resort) to resolve '{artist} - {title}'...")
            prompt = f"For the song '{title}' by artist '{artist}', what is the exact official title and artist to search on YouTube Music? Reply on a single line in format: ARTIST - TITLE"
            resp = client.models.generate_content(model=model_name, contents=prompt)
            ai_text = resp.text.strip()
            if '-' in ai_text:
                ai_parts = ai_text.split('-', 1)
                ai_query = f"{ai_parts[0].strip()} {ai_parts[1].strip()}"
                res = yt.search(ai_query, filter="songs", limit=3)
                if res and res[0].get('videoId'):
                    vid = res[0]['videoId']
                    logger.info(f"Auto-Fix (AI assisted) resolved '{artist} - {title}' [ID: {vid}]")
                    return {
                        'id': vid,
                        'title': title,
                        'artist': artist,
                        'primary_artist': primary,
                        'album': "Singles",
                        'fixed': True,
                        'method': 'ai_fallback'
                    }
        except Exception as e:
            logger.error(f"Failure in Auto-Fix level 3 (AI): {e}")

    # If all fails, retain previous ID
    return {
        'id': current_vid or '',
        'title': title,
        'artist': artist,
        'primary_artist': primary,
        'album': "Singles",
        'fixed': False,
        'method': 'none'
    }
