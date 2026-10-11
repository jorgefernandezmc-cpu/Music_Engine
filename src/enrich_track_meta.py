import os
import time
import logging
import urllib.request
import urllib.parse
import json
from collections import defaultdict
from typing import Dict, Any, Optional, Tuple, List
from mutagen.oggopus import OggOpus
from mutagen.mp4 import MP4
from thefuzz import fuzz

from src.db import get_db_connection
from src.album_resolver import get_primary_artist, resolve_album_metadata, resolve_song_release_date

logger = logging.getLogger('track_meta_enricher')
os.makedirs('logs', exist_ok=True)
if not logger.handlers:
    fh = logging.FileHandler('logs/track_meta.log')
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(fh)
    logger.setLevel(logging.INFO)


def apply_track_meta(file_path: str, track_number: Optional[int] = None, release_date: Optional[str] = None) -> bool:
    """
    Safely embeds tracknumber and date/year into physical audio file tags.
    Preserves all other tags intact (cover art, title, artist, lyrics, etc.).
    """
    if not file_path or not os.path.exists(file_path):
        return False

    changed = False
    try:
        if file_path.endswith('.opus'):
            audio = OggOpus(file_path)
            if track_number is not None:
                str_track = str(int(track_number))
                if audio.get("tracknumber") != [str_track]:
                    audio["tracknumber"] = str_track
                    changed = True
            if release_date:
                clean_date = str(release_date).strip()
                clean_year = clean_date[:4]
                if audio.get("date") != [clean_date]:
                    audio["date"] = clean_date
                    changed = True
                if audio.get("year") != [clean_year]:
                    audio["year"] = clean_year
                    changed = True
            if changed:
                audio.save()
                return True

        elif file_path.endswith('.m4a'):
            audio = MP4(file_path)
            if track_number is not None:
                trkn_val = [(int(track_number), 0)]
                if audio.get("trkn") != trkn_val:
                    audio["trkn"] = trkn_val
                    changed = True
            if release_date:
                clean_date = str(release_date).strip()
                if audio.get("\xa9day") != [clean_date]:
                    audio["\xa9day"] = clean_date
                    changed = True
            if changed:
                audio.save()
                return True
    except Exception as e:
        logger.warning(f"Error embedding metadata in {file_path}: {e}")

    return False


def fetch_deezer_track_meta(artist: str, title: str) -> Tuple[Optional[int], Optional[str]]:
    """
    Queries Deezer as a complimentary open source for track_position and release_date.
    """
    try:
        q = urllib.parse.quote(f"{get_primary_artist(artist)} {title}")
        url = f"https://api.deezer.com/search?q={q}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode())
            items = data.get('data', [])
            for item in items[:3]:
                d_tit = item.get('title', '')
                d_art = item.get('artist', {}).get('name', '')
                if fuzz.token_set_ratio(title.lower(), d_tit.lower()) >= 80 and fuzz.token_set_ratio(get_primary_artist(artist).lower(), d_art.lower()) >= 60:
                    track_id = item.get('id')
                    t_url = f"https://api.deezer.com/track/{track_id}"
                    with urllib.request.urlopen(t_url, timeout=4) as tresp:
                        tdata = json.loads(tresp.read().decode())
                        pos = tdata.get('track_position')
                        rdate = tdata.get('release_date')
                        return (int(pos) if pos else None, str(rdate) if rdate else None)
    except Exception as e:
        logger.debug(f"Deezer lookup unavailable for {artist} - {title}: {e}")
    return None, None


def enrich_library_metadata(db_path: str = "data/conveyor_state.sqlite",
                            force_all: bool = False,
                            limit: int = 0) -> Dict[str, Any]:
    """
    Enriches existing library embedding track numbers and release dates.
    Max efficiency strategy:
    1. Groups tracks by album to perform a single query per full album on YouTube Music.
    2. Matches album tracks assigning official track numbers (1, 2, 3...) and album year.
    3. For standalone singles, retrieves exact release date via get_song.
    4. Updates both SQLite database and physical audio files (.opus / .m4a).
    """
    from ytmusicapi import YTMusic
    yt = YTMusic()

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        if force_all:
            cursor.execute("""
                SELECT id, artist, title, album, file_path, track_number, release_date
                FROM tracks 
                WHERE file_path IS NOT NULL AND status IN ('PERMANENT', 'CINTA')
                ORDER BY added_at DESC
            """)
        else:
            cursor.execute("""
                SELECT id, artist, title, album, file_path, track_number, release_date
                FROM tracks 
                WHERE file_path IS NOT NULL 
                  AND status IN ('PERMANENT', 'CINTA')
                  AND (track_number IS NULL OR release_date IS NULL)
                ORDER BY added_at DESC
            """)
        rows = cursor.fetchall()

    if limit > 0:
        rows = rows[:limit]

    total_candidates = len(rows)
    logger.info(f"Starting track number and release date enrichment for {total_candidates} tracks...")

    # Group by (primary_artist, album)
    album_groups = defaultdict(list)
    for r in rows:
        t_id, artist, title, album, file_path, cur_track, cur_date = r
        p_artist = get_primary_artist(artist)
        alb_name = album or "Singles"
        album_groups[(p_artist, alb_name)].append(r)

    stats = {
        "total_songs": total_candidates,
        "albums_processed": 0,
        "tracks_assigned": 0,
        "dates_assigned": 0,
        "files_tagged": 0
    }

    album_cache: Dict[str, dict] = {}

    for (p_artist, alb_name), group_tracks in album_groups.items():
        stats["albums_processed"] += 1
        is_multi_or_named = len(group_tracks) > 1 and alb_name != "Singles"
        
        album_track_map: Dict[str, int] = {}
        album_year: Optional[str] = None
        
        if is_multi_or_named:
            cache_key = f"{p_artist} - {alb_name}".lower()
            alb_data = album_cache.get(cache_key)
            if alb_data is None:
                time.sleep(0.3)
                try:
                    search_res = yt.search(f"{p_artist} {alb_name}", filter="albums", limit=5)
                    for a_cand in search_res:
                        c_title = a_cand.get('title', '')
                        c_artists = [x.get('name', '') for x in a_cand.get('artists', [])]
                        art_match = any(fuzz.token_set_ratio(p_artist.lower(), ca.lower()) >= 60 for ca in c_artists) or not c_artists
                        if fuzz.ratio(alb_name.lower(), c_title.lower()) >= 80 and art_match:
                            b_id = a_cand.get('browseId')
                            if b_id:
                                alb_data = yt.get_album(b_id)
                                album_cache[cache_key] = alb_data
                                break
                    if alb_data is None:
                        album_cache[cache_key] = {}
                except Exception as e:
                    logger.debug(f"Album search failed for '{p_artist} - {alb_name}': {e}")
                    album_cache[cache_key] = {}
                    
            if alb_data:
                album_year = str(alb_data.get('year')) if alb_data.get('year') else None
                for idx, t_obj in enumerate(alb_data.get('tracks', []), 1):
                    t_vid = t_obj.get('videoId')
                    t_name = t_obj.get('title', '').strip().lower()
                    t_num = t_obj.get('trackNumber')
                    num_val = int(t_num) if t_num else idx
                    if t_vid:
                        album_track_map[t_vid] = num_val
                    if t_name:
                        album_track_map[t_name] = num_val

        # Process each track in the group
        for t_id, artist, title, album, file_path, cur_track, cur_date in group_tracks:
            clean_id = t_id.split('_')[0] if '_' in t_id else t_id
            resolved_track = cur_track
            resolved_date = cur_date

            # 1. Resolve track_number if missing
            if resolved_track is None:
                if clean_id in album_track_map:
                    resolved_track = album_track_map[clean_id]
                elif title.strip().lower() in album_track_map:
                    resolved_track = album_track_map[title.strip().lower()]
                else:
                    # Fuzzy search in album track list
                    for t_name, num_val in album_track_map.items():
                        if fuzz.ratio(title.strip().lower(), t_name) >= 85:
                            resolved_track = num_val
                            break

            # 2. If not multi-track album and no track assigned, default for single is 1
            if resolved_track is None and (alb_name == "Singles" or len(group_tracks) == 1):
                resolved_track = 1

            # 3. Resolve release_date if missing
            if not resolved_date:
                if album_year:
                    resolved_date = album_year
                else:
                    time.sleep(0.2)
                    try:
                        s_data = yt.get_song(clean_id)
                        micro = s_data.get('microformat', {}).get('microformatDataRenderer', {})
                        dt_str = micro.get('publishDate') or micro.get('uploadDate')
                        if dt_str:
                            resolved_date = dt_str.split('T')[0]
                    except Exception as se:
                        logger.debug(f"get_song failed for {clean_id}: {se}")

            # 4. Supplementary Deezer fallback if track number or date is still missing
            if resolved_track is None or not resolved_date:
                dz_track, dz_date = fetch_deezer_track_meta(artist, title)
                if resolved_track is None and dz_track:
                    resolved_track = dz_track
                if not resolved_date and dz_date:
                    resolved_date = dz_date

            # Update SQLite and physical file
            if resolved_track is not None or resolved_date:
                with get_db_connection(db_path) as conn:
                    conn.execute("""
                        UPDATE tracks 
                        SET track_number = COALESCE(?, track_number), 
                            release_date = COALESCE(?, release_date) 
                        WHERE id = ?
                    """, (resolved_track, resolved_date, t_id))
                    conn.commit()

                if resolved_track is not None and cur_track is None:
                    stats["tracks_assigned"] += 1
                if resolved_date and not cur_date:
                    stats["dates_assigned"] += 1

                if file_path and os.path.exists(file_path):
                    if apply_track_meta(file_path, track_number=resolved_track, release_date=resolved_date):
                        stats["files_tagged"] += 1
                        logger.info(f"[ENRICHED] {artist} - {title} => Track: {resolved_track}, Date: {resolved_date}")

    logger.info(f"Finished enrichment: {stats}")
    return stats
