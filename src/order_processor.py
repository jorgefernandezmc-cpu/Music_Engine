"""
order_processor.py
Module for processing and executing remote requests and commands:
- Requests mailbox peticiones.txt (natural language and direct commands).
- CLI commands (set-album, fix, etc.).
- Physical album reassignment, genre correction, lyrics, promotion, and purging.
"""

import os
import re
import shutil
import logging
import urllib.request
import json
from urllib.parse import urlparse, parse_qs
from thefuzz import fuzz
from mutagen.oggopus import OggOpus
from mutagen.mp4 import MP4
from mutagen.mp3 import MP3
from mutagen.flac import FLAC

from src.db import get_db_connection
from src.paths import StoragePaths, sanitize_filename, DEFAULT_REQUESTS_HEADER, DEFAULT_PETICIONES_HEADER, get_mailbox_header
from src.notifications import send_notification
from src.album_resolver import get_primary_artist, auto_fix_track, resolve_album_track
from src.genre_resolver import clean_genre_string, apply_genre_metadata, resolve_genre
from src.enrich_lyrics import check_and_upgrade_track

logger = logging.getLogger('order_processor')

DEFAULT_ANTOJOS_HEADER = DEFAULT_PETICIONES_HEADER


def _remove_from_download_archive(video_id: str, archive_path: str = "data/download_archive.txt"):
    """Removes a video ID from yt-dlp download archive so it can be re-downloaded fresh."""
    if not video_id or not os.path.exists(archive_path):
        return
    try:
        with open(archive_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        new_lines = [l for l in lines if video_id not in l]
        if len(new_lines) != len(lines):
            with open(archive_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
    except Exception:
        pass


def extract_url_info(raw_url: str) -> dict | None:
    """
    Parses YouTube, YouTube Music, or Spotify URLs.
    Returns dict: {'provider': 'youtube'|'spotify', 'type': 'video'|'playlist'|'track'|'album', 'id': str, 'url': str} or None.
    """
    if not raw_url:
        return None
    clean_url = raw_url.strip().strip('<>()"\'')
    try:
        parsed = urlparse(clean_url)
        netloc = parsed.netloc.lower()
        if not netloc:
            return None

        # Spotify
        if 'spotify.com' in netloc:
            parts = [p for p in parsed.path.split('/') if p]
            if len(parts) >= 2 and parts[0] in ('track', 'album', 'playlist'):
                return {'provider': 'spotify', 'type': parts[0], 'id': parts[1].split('?')[0], 'url': clean_url}

        # YouTube short url
        if 'youtu.be' in netloc:
            vid = parsed.path.lstrip('/').split('?')[0].split('&')[0]
            if vid:
                return {'provider': 'youtube', 'type': 'video', 'id': vid, 'url': clean_url}

        # YouTube / YouTube Music
        if 'youtube.com' in netloc:
            qs = parse_qs(parsed.query)
            if 'v' in qs and qs['v']:
                return {'provider': 'youtube', 'type': 'video', 'id': qs['v'][0], 'url': clean_url}
            if 'list' in qs and qs['list']:
                return {'provider': 'youtube', 'type': 'playlist', 'id': qs['list'][0], 'url': clean_url}
            if parsed.path.startswith('/shorts/'):
                vid = parsed.path.split('/shorts/')[1].split('/')[0].split('?')[0]
                if vid:
                    return {'provider': 'youtube', 'type': 'video', 'id': vid, 'url': clean_url}

    except Exception as e:
        logger.debug(f"Error parsing URL '{raw_url}': {e}")
    return None


class OrderProcessor:
    """Processes commands and requests mailbox for Music Engine."""

    def __init__(self, db_path: str, config_path: str, paths=None, playlists=None, curator=None):
        self.db_path = db_path
        self.config_path = config_path
        self.paths = paths or StoragePaths(config_path)
        self.playlists = playlists
        self.curator = curator

    def _find_best_track_match(self, tracks: list[tuple], query: str, min_score: int = 75):
        """
        Optimized in-memory track matching:
        1. Exact match shortcut (artist - title or title).
        2. Disambiguation if artist is supplied (e.g. 'Artist - Title' or 'Title by/de Artist').
        3. Fuzzy matching with token_set_ratio.
        """
        clean_q = query.strip().strip('"\'').lower()
        if not clean_q or not tracks:
            return None, 0

        # Disambiguation parts
        q_artist, q_title = None, None
        if " - " in clean_q:
            parts = clean_q.split(" - ", 1)
            q_artist, q_title = parts[0].strip(), parts[1].strip()
        elif re.search(r'\s+(?:by|de)\s+', clean_q, re.IGNORECASE):
            parts = re.split(r'\s+(?:by|de)\s+', clean_q, flags=re.IGNORECASE)
            q_title, q_artist = parts[0].strip(), parts[1].strip()

        # Step 1: Exact quick shortcut
        for cand in tracks:
            c_art = str(cand[1] or "").lower()
            c_tit = str(cand[2] or "").lower()
            if q_artist and q_title:
                if (q_artist == c_art or q_artist in c_art) and (q_title == c_tit):
                    return cand, 100
            if clean_q == c_tit or clean_q == f"{c_art} {c_tit}" or clean_q == f"{c_art} - {c_tit}":
                return cand, 100

        # Step 2: Fuzzy search with artist-title weighting when disambiguated
        best_cand = None
        best_score = 0
        for cand in tracks:
            c_art = str(cand[1] or "").lower()
            c_tit = str(cand[2] or "").lower()

            if q_artist and q_title:
                s_art = fuzz.token_set_ratio(q_artist, c_art)
                s_tit = fuzz.token_set_ratio(q_title, c_tit)
                if s_art < 45 and s_tit < 95:
                    score = int(0.2 * s_art + 0.3 * s_tit)
                else:
                    score = int(0.4 * s_art + 0.6 * s_tit)
            else:
                s1 = fuzz.token_set_ratio(clean_q, f"{c_art} {c_tit}")
                s2 = fuzz.token_set_ratio(clean_q, c_tit)
                score = max(s1, s2)

            if score > best_score:
                best_score = score
                best_cand = cand
                if best_score == 100:
                    break

        if best_cand and best_score >= min_score:
            return best_cand, best_score
        return None, best_score

    def process_album_move(self, conn, song_query: str, new_album: str) -> tuple[bool, str]:
        """
        Reassigns a permanent track to a specific album and physically moves its files and lyrics.
        Returns (success: bool, message: str).
        """
        clean_q = song_query.strip().strip('"\'')
        clean_album = new_album.strip().strip('"\'*.')

        cursor = conn.cursor()
        cursor.execute("SELECT id, artist, title, album, file_path FROM tracks WHERE status = 'PERMANENT'")
        perm_tracks = cursor.fetchall()

        best_cand, best_score = self._find_best_track_match(perm_tracks, clean_q, min_score=80)
        if not best_cand:
            logger.warning(f"No matching track found in Permanent for: '{song_query}'")
            return False, f"Track '{song_query}' not found in Permanent"

        t_id, t_art, t_tit, old_alb, old_fpath = best_cand
        p_artist = get_primary_artist(t_art)
        ext = os.path.splitext(old_fpath)[1] if old_fpath else '.opus'
        new_fpath = self.paths.get_permanente_track_path(p_artist, clean_album, t_tit, ext=ext)
        os.makedirs(os.path.dirname(new_fpath), exist_ok=True)

        if old_fpath and os.path.exists(old_fpath) and old_fpath != new_fpath:
            shutil.move(old_fpath, new_fpath)
            old_lrc = os.path.splitext(old_fpath)[0] + ".lrc"
            new_lrc = os.path.splitext(new_fpath)[0] + ".lrc"
            if os.path.exists(old_lrc):
                shutil.move(old_lrc, new_lrc)

            old_dir = os.path.dirname(old_fpath)
            try:
                if os.path.exists(old_dir) and not os.listdir(old_dir):
                    os.rmdir(old_dir)
            except Exception:
                pass

            if new_fpath.endswith('.opus'):
                try:
                    audio = OggOpus(new_fpath)
                    audio["album"] = clean_album
                    audio.save()
                except Exception as me:
                    logger.error(f"Error updating album tag: {me}")
            elif new_fpath.endswith('.m4a'):
                try:
                    audio = MP4(new_fpath)
                    audio["\xa9alb"] = clean_album
                    audio.save()
                except Exception as me:
                    logger.error(f"Error updating album tag: {me}")

        cursor.execute("UPDATE tracks SET album = ?, file_path = ? WHERE id = ?", (clean_album, new_fpath, t_id))
        conn.commit()
        logger.info(f"Album updated: '{t_tit}' ({t_art}) reassigned to '{clean_album}'")
        send_notification("Album Updated", f"{t_tit}\nMoved to: {clean_album}")
        if self.playlists:
            self.playlists.update_permanent_playlists()
        return True, f"'{t_tit}' ({t_art}) reassigned to '{clean_album}' -> {new_fpath}"

    def process_genre_update(self, conn, song_query: str, new_genre: str = None) -> tuple[bool, str]:
        """
        Updates musical genre in SQLite and physical metadata (.opus / .m4a).
        If new_genre is None or empty, automatically re-analyzes genre using APIs and AI.
        """
        clean_q = song_query.strip().strip('"\'')
        cursor = conn.cursor()
        cursor.execute("SELECT id, artist, title, genre, file_path FROM tracks WHERE file_path IS NOT NULL AND status IN ('PERMANENT', 'CINTA')")
        all_tracks = cursor.fetchall()

        best_cand, best_score = self._find_best_track_match(all_tracks, clean_q, min_score=75)
        if not best_cand:
            return False, f"Track '{clean_q}' not found in your library"

        t_id, t_art, t_tit, old_gen, t_fpath = best_cand

        if new_genre and new_genre.strip():
            final_genre = clean_genre_string(new_genre.strip())
        else:
            final_genre = resolve_genre(t_art, t_tit, db_path=self.db_path, allow_ai=True)

        cursor.execute("UPDATE tracks SET genre = ? WHERE id = ?", (final_genre, t_id))
        conn.commit()

        if t_fpath and os.path.exists(t_fpath):
            apply_genre_metadata(t_fpath, final_genre)

        logger.info(f"Genre updated: '{t_art} - {t_tit}' from '{old_gen}' to '{final_genre}'")
        send_notification("Genre Updated", f"{t_art} - {t_tit}\nNew genre: {final_genre}")
        return True, f"'{t_art} - {t_tit}' updated to '{final_genre}'"

    def process_lyrics_update(self, conn, song_query: str) -> tuple[bool, str]:
        """
        Forces search, update, and synchronization of lyrics for a specific track.
        Removes existing .lrc to force a verified fresh version from providers.
        """
        clean_q = song_query.strip().strip('"\'')
        cursor = conn.cursor()
        cursor.execute("SELECT id, artist, title, file_path, duration_seconds FROM tracks WHERE file_path IS NOT NULL AND status IN ('PERMANENT', 'CINTA')")
        all_tracks = cursor.fetchall()

        best_cand, best_score = self._find_best_track_match(all_tracks, clean_q, min_score=75)
        if not best_cand:
            return False, f"Track '{clean_q}' not found in your library"

        t_id, t_art, t_tit, t_fpath, t_dur = best_cand

        base_path = os.path.splitext(t_fpath)[0]
        lrc_path = f"{base_path}.lrc"
        if os.path.exists(lrc_path):
            try:
                os.remove(lrc_path)
            except Exception:
                pass

        was_updated, msg = check_and_upgrade_track(t_id, t_tit, t_art, t_fpath, duration=t_dur)
        if was_updated:
            send_notification("Lyrics Updated", f"{t_art} - {t_tit}\n{msg}")
            return True, f"Lyrics for '{t_art} - {t_tit}' updated successfully"
        else:
            return False, f"No verified lyrics found for '{t_art} - {t_tit}': {msg}"

    def process_promote_track(self, conn, song_query: str) -> tuple[bool, str]:
        """
        Immediately promotes a song from Conveyor or Cravings to Permanent, moving it to artist/album folder.
        """
        clean_q = song_query.strip().strip('"\'')
        cursor = conn.cursor()
        cursor.execute("SELECT id, artist, title, album, file_path, status FROM tracks WHERE status IN ('CINTA', 'ANTOJO')")
        candidates = cursor.fetchall()

        cand_for_match = [(c[0], c[1], c[2]) for c in candidates]
        best_cand, best_score = self._find_best_track_match(cand_for_match, clean_q, min_score=75)
        if not best_cand:
            return False, f"Track '{clean_q}' not found in Conveyor or Cravings"

        cand_map = {c[0]: c for c in candidates}
        t_id, t_art, t_tit, t_alb, t_fpath, t_prev_status = cand_map[best_cand[0]]
        p_artist = get_primary_artist(t_art)
        ext = os.path.splitext(t_fpath)[1] if t_fpath else '.opus'
        clean_alb = t_alb if t_alb else "Singles"
        new_path = self.paths.get_permanente_track_path(p_artist, clean_alb, t_tit, ext=ext)
        os.makedirs(os.path.dirname(new_path), exist_ok=True)

        if t_fpath and os.path.exists(t_fpath):
            old_dir = os.path.dirname(t_fpath)
            shutil.move(t_fpath, new_path)
            old_lrc = os.path.splitext(t_fpath)[0] + ".lrc"
            new_lrc = os.path.splitext(new_path)[0] + ".lrc"
            if os.path.exists(old_lrc):
                shutil.move(old_lrc, new_lrc)

            # Clean empty directory if it was under Cravings
            try:
                if old_dir and os.path.exists(old_dir) and not os.listdir(old_dir):
                    os.rmdir(old_dir)
                    parent_old = os.path.dirname(old_dir)
                    if parent_old and os.path.exists(parent_old) and not os.listdir(parent_old) and parent_old != self.paths.cravings_dir:
                        os.rmdir(parent_old)
            except Exception:
                pass

        cursor.execute("UPDATE tracks SET status = 'PERMANENT', is_permanent = 1, file_path = ? WHERE id = ?", (new_path, t_id))
        conn.commit()
        send_notification("Shielded in Permanent", f"{t_art} - {t_tit}\nMoved to Permanent/{p_artist}/{clean_alb}")
        if self.playlists:
            self.playlists.update_all_playlists()
        return True, f"'{t_art} - {t_tit}' promoted to Permanent"

    def process_purge_track(self, conn, song_query: str) -> tuple[bool, str]:
        """
        Immediately purges a track from Conveyor or Cravings and marks it as PURGED to prevent re-downloads.
        """
        clean_q = song_query.strip().strip('"\'')
        cursor = conn.cursor()
        cursor.execute("SELECT id, artist, title, file_path, status FROM tracks WHERE status IN ('CINTA', 'ANTOJO')")
        candidates = cursor.fetchall()

        cand_for_match = [(c[0], c[1], c[2]) for c in candidates]
        best_cand, best_score = self._find_best_track_match(cand_for_match, clean_q, min_score=75)
        if not best_cand:
            return False, f"Track '{clean_q}' not found in Conveyor or Cravings"

        cand_map = {c[0]: c for c in candidates}
        t_id, t_art, t_tit, t_fpath, t_status = cand_map[best_cand[0]]
        if t_fpath and os.path.exists(t_fpath):
            old_dir = os.path.dirname(t_fpath)
            try:
                os.remove(t_fpath)
            except Exception:
                pass
            old_lrc = os.path.splitext(t_fpath)[0] + ".lrc"
            if os.path.exists(old_lrc):
                try:
                    os.remove(old_lrc)
                except Exception:
                    pass

            # Clean empty directory if under Cravings
            try:
                if old_dir and os.path.exists(old_dir) and not os.listdir(old_dir):
                    os.rmdir(old_dir)
                    parent_old = os.path.dirname(old_dir)
                    if parent_old and os.path.exists(parent_old) and not os.listdir(parent_old) and parent_old != self.paths.cravings_dir:
                        os.rmdir(parent_old)
            except Exception:
                pass

        cursor.execute("UPDATE tracks SET status = 'PURGED' WHERE id = ?", (t_id,))
        conn.commit()
        origin = "Cravings" if t_status == 'ANTOJO' else "Conveyor"
        send_notification("Track Purged", f"{t_art} - {t_tit}\nRemoved from {origin}")
        if self.playlists:
            self.playlists.update_all_playlists()
        return True, f"'{t_art} - {t_tit}' purged from {origin}"

    def process_purge_permanent(self, conn, song_query: str) -> tuple[bool, str]:
        """
        Immediately purges a track from Permanent library, removes physical file and .lrc,
        cleans empty artist/album directories, and marks track as PURGED.
        """
        clean_q = song_query.strip().strip('"\'')
        cursor = conn.cursor()
        cursor.execute("SELECT id, artist, title, file_path, album FROM tracks WHERE status = 'PERMANENT'")
        candidates = cursor.fetchall()

        cand_for_match = [(c[0], c[1], c[2]) for c in candidates]
        best_cand, best_score = self._find_best_track_match(cand_for_match, clean_q, min_score=70)
        if not best_cand:
            return False, f"Track '{clean_q}' not found in Permanent collection"

        cand_map = {c[0]: c for c in candidates}
        t_id, t_art, t_tit, t_fpath, t_alb = cand_map[best_cand[0]]
        if t_fpath and os.path.exists(t_fpath):
            old_dir = os.path.dirname(t_fpath)
            try:
                os.remove(t_fpath)
            except Exception:
                pass
            old_lrc = os.path.splitext(t_fpath)[0] + ".lrc"
            if os.path.exists(old_lrc):
                try:
                    os.remove(old_lrc)
                except Exception:
                    pass

            # Clean empty album and artist directory
            try:
                if old_dir and os.path.exists(old_dir) and not os.listdir(old_dir):
                    os.rmdir(old_dir)
                    parent_old = os.path.dirname(old_dir)
                    if parent_old and os.path.exists(parent_old) and not os.listdir(parent_old) and parent_old != self.paths.permanente_dir:
                        os.rmdir(parent_old)
            except Exception:
                pass

        _remove_from_download_archive(t_id)
        cursor.execute("UPDATE tracks SET status = 'PURGED', is_permanent = 0 WHERE id = ?", (t_id,))
        conn.commit()
        send_notification("Permanent Track Purged", f"{t_art} - {t_tit}\nRemoved from Permanent")
        if self.playlists:
            self.playlists.update_all_playlists()
        return True, f"'{t_art} - {t_tit}' purged from Permanent"

    def process_artist_move(self, conn, song_query: str, new_artist: str) -> tuple[bool, str]:
        """
        Reassigns primary artist of a song, moves physical files, updates audio tags, and updates SQLite.
        """
        clean_q = song_query.strip().strip('"\'')
        clean_artist = new_artist.strip().strip('"\'*.')
        if not clean_artist:
            return False, "Target artist cannot be empty"

        cursor = conn.cursor()
        cursor.execute("SELECT id, artist, title, album, file_path, status FROM tracks WHERE file_path IS NOT NULL AND status IN ('PERMANENT', 'CINTA', 'ANTOJO')")
        all_tracks = cursor.fetchall()

        cand_for_match = [(c[0], c[1], c[2]) for c in all_tracks]
        best_cand, best_score = self._find_best_track_match(cand_for_match, clean_q, min_score=70)
        if not best_cand:
            return False, f"Track '{clean_q}' not found in library"

        cand_map = {c[0]: c for c in all_tracks}
        t_id, old_art, t_tit, t_alb, old_fpath, t_status = cand_map[best_cand[0]]
        ext = os.path.splitext(old_fpath)[1] if old_fpath else '.opus'
        clean_alb = t_alb if t_alb else "Singles"

        if t_status == 'PERMANENT':
            new_fpath = self.paths.get_permanente_track_path(clean_artist, clean_alb, t_tit, ext=ext)
        elif t_status == 'ANTOJO':
            new_fpath = self.paths.get_craving_track_path(clean_artist, clean_alb, t_tit, ext=ext)
        else:
            new_fpath = old_fpath

        if old_fpath and os.path.exists(old_fpath) and old_fpath != new_fpath:
            os.makedirs(os.path.dirname(new_fpath), exist_ok=True)
            shutil.move(old_fpath, new_fpath)
            old_lrc = os.path.splitext(old_fpath)[0] + ".lrc"
            new_lrc = os.path.splitext(new_fpath)[0] + ".lrc"
            if os.path.exists(old_lrc):
                shutil.move(old_lrc, new_lrc)

            old_dir = os.path.dirname(old_fpath)
            try:
                if old_dir and os.path.exists(old_dir) and not os.listdir(old_dir):
                    os.rmdir(old_dir)
                    parent_old = os.path.dirname(old_dir)
                    if parent_old and os.path.exists(parent_old) and not os.listdir(parent_old) and parent_old != self.paths.permanente_dir:
                        os.rmdir(parent_old)
            except Exception:
                pass
        else:
            new_fpath = old_fpath

        # Update physical audio tags
        target_file = new_fpath if (new_fpath and os.path.exists(new_fpath)) else old_fpath
        if target_file and os.path.exists(target_file):
            if target_file.endswith('.opus'):
                try:
                    audio = OggOpus(target_file)
                    audio["artist"] = clean_artist
                    audio.save()
                except Exception as e:
                    logger.error(f"Error updating artist tag: {e}")
            elif target_file.endswith('.m4a'):
                try:
                    audio = MP4(target_file)
                    audio["\xa9ART"] = clean_artist
                    audio.save()
                except Exception as e:
                    logger.error(f"Error updating artist tag: {e}")
            elif target_file.endswith('.flac'):
                try:
                    audio = FLAC(target_file)
                    audio["artist"] = clean_artist
                    audio.save()
                except Exception as e:
                    logger.error(f"Error updating artist tag: {e}")

        cursor.execute("UPDATE tracks SET artist = ?, file_path = ? WHERE id = ?", (clean_artist, new_fpath, t_id))
        conn.commit()
        logger.info(f"Artist updated: '{t_tit}' from '{old_art}' to '{clean_artist}'")
        send_notification("Artist Updated", f"{t_tit}\nNew artist: {clean_artist}")
        if self.playlists:
            self.playlists.update_all_playlists()
        return True, f"'{t_tit}' ({old_art}) updated to artist '{clean_artist}'"

    def process_direct_url(self, conn, raw_url: str, is_craving: bool = False) -> tuple[bool, str]:
        """
        Processes direct audio/video/playlist URLs (YouTube, YouTube Music, or Spotify).
        """
        url_info = extract_url_info(raw_url)
        if not url_info:
            return False, f"Unsupported or invalid URL: '{raw_url}'"

        provider = url_info['provider']
        item_type = url_info['type']
        item_id = url_info['id']

        # 1. Spotify via oEmbed
        if provider == 'spotify':
            try:
                oembed_url = f"https://open.spotify.com/oembed?url={raw_url.strip()}"
                req = urllib.request.Request(oembed_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=7) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                title = data.get('title', '')
                if not title:
                    return False, f"Could not extract title from Spotify URL '{raw_url}'"
                if item_type == 'album':
                    return self.download_album(conn, title, is_craving=is_craving)
                else:
                    return self.download_single_track(conn, title, is_craving=is_craving)
            except Exception as e:
                logger.error(f"Error resolving Spotify URL '{raw_url}': {e}")
                return False, f"Could not resolve Spotify URL: {e}"

        # 2. YouTube Playlist
        if provider == 'youtube' and item_type == 'playlist':
            import yt_dlp
            try:
                ydl_opts = {'extract_flat': True, 'quiet': True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(raw_url, download=False)
                entries = info.get('entries', []) if info else []
                if not entries:
                    return False, f"No entries found in YouTube playlist '{raw_url}'"

                pl_title = info.get('title') or "Playlist"
                cursor = conn.cursor()
                queued_count = 0
                is_perm = 0 if is_craving else 1
                target_folder = "Cravings" if is_craving else "Permanent"

                for idx, entry in enumerate(entries, start=1):
                    vid = entry.get('id')
                    if not vid:
                        continue
                    t_title = entry.get('title') or 'Unknown Title'
                    uploader = entry.get('uploader') or entry.get('channel') or 'Various Artists'
                    t_dur = int(entry.get('duration') or 0)

                    safe_title = sanitize_filename(t_title)
                    safe_artist = sanitize_filename(get_primary_artist(uploader))
                    safe_album = sanitize_filename(pl_title)

                    if is_craving:
                        f_path = self.paths.get_craving_track_path(safe_artist, safe_album, safe_title)
                    else:
                        f_path = self.paths.get_permanente_track_path(safe_artist, safe_album, safe_title)

                    _remove_from_download_archive(vid)
                    cursor.execute("SELECT status FROM tracks WHERE id = ?", (vid,))
                    existing = cursor.fetchone()
                    if existing:
                        cursor.execute("""
                            UPDATE tracks 
                            SET status = 'PENDING', file_path = ?, is_permanent = ?, album = ?, track_number = ?
                            WHERE id = ?
                        """, (f_path, is_perm, pl_title, idx, vid))
                    else:
                        cursor.execute("""
                            INSERT INTO tracks (id, title, artist, album, duration_seconds, status, is_permanent, file_path, track_number)
                            VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?, ?)
                        """, (vid, t_title, uploader, pl_title, t_dur, is_perm, f_path, idx))
                    queued_count += 1

                conn.commit()
                send_notification("Album Queued", f"{pl_title}\n{queued_count}/{len(entries)} tracks queued to {target_folder}")
                return True, f"Playlist '{pl_title}' ({queued_count}/{len(entries)} tracks) queued to {target_folder}"
            except Exception as e:
                logger.error(f"Error processing YouTube playlist URL '{raw_url}': {e}")
                return False, f"Error processing YouTube playlist: {e}"

        # 3. YouTube Single Video
        if provider == 'youtube' and item_type == 'video':
            from ytmusicapi import YTMusic
            yt = self.curator.yt if (self.curator and hasattr(self.curator, 'yt')) else YTMusic()
            title = None
            artist = None
            dur = 0
            try:
                song_data = yt.get_song(item_id)
                v_details = song_data.get('videoDetails', {}) if song_data else {}
                title = v_details.get('title')
                artist = v_details.get('author')
                dur = int(v_details.get('lengthSeconds') or 0)
            except Exception:
                pass

            if not title or not artist:
                import yt_dlp
                try:
                    with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                        inf = ydl.extract_info(f"https://www.youtube.com/watch?v={item_id}", download=False)
                    title = inf.get('title') or f"Track {item_id}"
                    artist = inf.get('uploader') or "Unknown Artist"
                    dur = int(inf.get('duration') or 0)
                except Exception as ex:
                    return False, f"Could not fetch metadata for YouTube ID '{item_id}': {ex}"

            primary_art = get_primary_artist(artist)
            safe_title = sanitize_filename(title)
            safe_artist = sanitize_filename(primary_art)
            safe_album = "Singles"

            is_perm = 0 if is_craving else 1
            target_folder = "Cravings" if is_craving else "Permanent"
            if is_craving:
                f_path = self.paths.get_craving_track_path(safe_artist, safe_album, safe_title)
            else:
                f_path = self.paths.get_permanente_track_path(safe_artist, safe_album, safe_title)

            _remove_from_download_archive(item_id)
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM tracks WHERE id = ?", (item_id,))
            row = cursor.fetchone()
            if row:
                cursor.execute("""
                    UPDATE tracks 
                    SET status = 'PENDING', file_path = ?, is_permanent = ?, title = ?, artist = ?, album = ?, duration_seconds = ?
                    WHERE id = ?
                """, (f_path, is_perm, title, artist, safe_album, dur, item_id))
            else:
                cursor.execute("""
                    INSERT INTO tracks (id, title, artist, album, duration_seconds, status, is_permanent, file_path)
                    VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?)
                """, (item_id, title, artist, safe_album, dur, is_perm, f_path))

            conn.commit()
            send_notification("Track Queued", f"{artist} - {title}\nQueued to {target_folder}")
            return True, f"'{artist} - {title}' (ID: {item_id}) queued to {target_folder}"

        return False, f"Unsupported URL action for: {raw_url}"

    def process_redownload_track(self, conn, song_query: str) -> tuple[bool, str]:
        """
        Forces re-download of an existing track from scratch, deleting the local file and resetting to PENDING.
        """
        clean_q = song_query.strip().strip('"\'')
        cursor = conn.cursor()
        cursor.execute("SELECT id, artist, title, file_path FROM tracks WHERE file_path IS NOT NULL")
        all_tracks = cursor.fetchall()
        best_cand, best_score = self._find_best_track_match(all_tracks, clean_q, min_score=70)
        if not best_cand:
            return False, f"Track '{clean_q}' not found in library"

        t_id, t_art, t_tit, t_fpath = best_cand
        if t_fpath and os.path.exists(t_fpath):
            try:
                os.remove(t_fpath)
            except Exception:
                pass
            old_lrc = os.path.splitext(t_fpath)[0] + ".lrc"
            if os.path.exists(old_lrc):
                try:
                    os.remove(old_lrc)
                except Exception:
                    pass

        _remove_from_download_archive(t_id)
        cursor.execute("UPDATE tracks SET status = 'PENDING' WHERE id = ?", (t_id,))
        conn.commit()
        send_notification("Redownload Queued", f"{t_art} - {t_tit}\nAudio will be re-downloaded")
        return True, f"'{t_art} - {t_tit}' queued for fresh re-download"

    def process_info_track(self, conn, song_query: str) -> tuple[bool, str]:
        """
        Inspects an audio track in the library and returns a formatted information string.
        """
        clean_q = song_query.strip().strip('"\'')
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, artist, title, album, genre, status, duration_seconds, release_date, track_number, file_path 
            FROM tracks 
            WHERE file_path IS NOT NULL
        """)
        all_tracks = cursor.fetchall()
        cand_for_match = [(c[0], c[1], c[2]) for c in all_tracks]
        best_cand, best_score = self._find_best_track_match(cand_for_match, clean_q, min_score=70)
        if not best_cand:
            return False, f"Track '{clean_q}' not found in library"

        cand_map = {c[0]: c for c in all_tracks}
        t_id, t_art, t_tit, t_alb, t_gen, t_stat, t_dur, t_rel, t_num, t_fpath = cand_map[best_cand[0]]

        # Formatting duration
        dur_str = f"{t_dur // 60}:{t_dur % 60:02d}" if (t_dur and t_dur > 0) else "Unknown"

        # Checking physical file
        f_info = "Missing file"
        lrc_info = "No"
        if t_fpath and os.path.exists(t_fpath):
            size_mb = os.path.getsize(t_fpath) / (1024 * 1024)
            ext = os.path.splitext(t_fpath)[1].lstrip('.').upper()
            f_info = f"{ext} ({size_mb:.1f} MB)"
            lrc_path = os.path.splitext(t_fpath)[0] + ".lrc"
            if os.path.exists(lrc_path):
                lrc_info = "Synced (.lrc)"

        is_es = (self.paths.language == "es")
        lbl_album = "Álbum" if is_es else "Album"
        lbl_genre = "Género" if is_es else "Genre"
        lbl_status = "Estado" if is_es else "Status"
        lbl_dur = "Duración" if is_es else "Duration"
        lbl_file = "Archivo" if is_es else "File"
        lbl_lyrics = "Letra" if is_es else "Lyrics"

        year_str = f" ({t_rel[:4]})" if (t_rel and len(t_rel) >= 4) else ""
        num_str = f" #{t_num}" if t_num else ""
        album_str = f"{t_alb or 'Singles'}{year_str}{num_str}"

        info_line = (
            f"[INFO] {t_art} - {t_tit} | {lbl_album}: {album_str} | "
            f"{lbl_genre}: {t_gen or 'Unknown'} | {lbl_status}: {t_stat} | "
            f"{lbl_dur}: {dur_str} | {lbl_file}: {f_info} | {lbl_lyrics}: {lrc_info}"
        )
        return True, info_line

    def process_playlist_command(self, conn, pl_name: str, op: str, song_query: str) -> tuple[bool, str]:
        """
        Adds (+=) or removes (-=) a song from a personal playlist in user_playlists_dir.
        """
        clean_pl = sanitize_filename(pl_name.strip().strip('"\''))
        clean_q = song_query.strip().strip('"\'')
        if not clean_pl or not clean_q:
            return False, "Invalid playlist or song specification"

        cursor = conn.cursor()
        cursor.execute("SELECT id, artist, title, file_path, duration_seconds FROM tracks WHERE file_path IS NOT NULL AND status IN ('PERMANENT', 'CINTA', 'ANTOJO')")
        all_tracks = cursor.fetchall()
        best_cand, best_score = self._find_best_track_match(all_tracks, clean_q, min_score=70)
        if not best_cand:
            return False, f"Track '{clean_q}' not found in library"

        t_id, t_art, t_tit, t_fpath, t_dur = best_cand
        if not t_fpath or not os.path.exists(t_fpath):
            return False, f"Audio file for '{t_art} - {t_tit}' does not exist on disk"

        user_pl_dir = os.path.join(self.paths.playlists_dir, "Listas Propias")
        if self.playlists and hasattr(self.playlists, 'user_playlists_dir'):
            user_pl_dir = self.playlists.user_playlists_dir
        os.makedirs(user_pl_dir, exist_ok=True)
        m3u8_path = os.path.join(user_pl_dir, f"{clean_pl}.m3u8")

        existing_lines = []
        if os.path.exists(m3u8_path):
            try:
                with open(m3u8_path, 'r', encoding='utf-8') as f:
                    existing_lines = f.readlines()
            except Exception:
                existing_lines = []

        dur_val = t_dur if (t_dur and t_dur > 0) else -1
        display_name = f"{t_art} - {t_tit}"
        rel_path = os.path.relpath(t_fpath, user_pl_dir)

        if op == '+=':
            for line in existing_lines:
                if line.strip() in (rel_path, t_fpath):
                    return True, f"'{display_name}' already in playlist '{clean_pl}'"

            with open(m3u8_path, 'a' if existing_lines else 'w', encoding='utf-8') as f:
                if not existing_lines:
                    f.write("#EXTM3U\n")
                f.write(f"#EXTINF:{dur_val},{display_name}\n")
                f.write(f"{rel_path}\n")

            send_notification("Playlist Updated", f"{display_name}\nAdded to playlist {clean_pl}")
            if self.playlists:
                self.playlists.update_all_playlists()
            return True, f"'{display_name}' added to playlist '{clean_pl}'"

        elif op == '-=':
            if not existing_lines:
                return False, f"Playlist '{clean_pl}' does not exist or is empty"

            new_lines = []
            skip_next = False
            removed = False
            for i, line in enumerate(existing_lines):
                s_line = line.strip()
                if skip_next:
                    skip_next = False
                    continue
                if s_line.startswith("#EXTINF") and i + 1 < len(existing_lines):
                    next_line = existing_lines[i + 1].strip()
                    if next_line in (rel_path, t_fpath):
                        skip_next = True
                        removed = True
                        continue
                if s_line in (rel_path, t_fpath):
                    removed = True
                    continue
                new_lines.append(line)

            if not removed:
                return False, f"Track '{display_name}' was not found in playlist '{clean_pl}'"

            with open(m3u8_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)

            send_notification("Playlist Updated", f"{display_name}\nRemoved from playlist {clean_pl}")
            if self.playlists:
                self.playlists.update_all_playlists()
            return True, f"'{display_name}' removed from playlist '{clean_pl}'"

        return False, f"Unsupported playlist operator '{op}'"

    def download_album(self, conn, artist_or_query: str, album_name: str = None, is_craving: bool = False) -> tuple[bool, str]:
        """
        Searches and queues all tracks from an official album via YouTube Music.
        Queues tracks as PENDING into either Cravings or Permanent.
        """
        from ytmusicapi import YTMusic
        yt = self.curator.yt if (self.curator and hasattr(self.curator, 'yt')) else YTMusic()

        clean_q = artist_or_query.strip().strip('"\'')
        if album_name and album_name.strip():
            search_query = f"{clean_q} {album_name.strip()}".strip()
        else:
            if " - " in clean_q:
                parts = clean_q.split(" - ", 1)
                search_query = f"{parts[0].strip()} {parts[1].strip()}"
            elif re.search(r'\s+(?:by|de)\s+', clean_q, re.IGNORECASE):
                parts = re.split(r'\s+(?:by|de)\s+', clean_q, flags=re.IGNORECASE)
                search_query = f"{parts[1].strip()} {parts[0].strip()}"
            else:
                search_query = clean_q

        try:
            results = yt.search(search_query, filter="albums")
        except Exception as e:
            logger.error(f"Error searching album '{search_query}': {e}")
            return False, f"Error searching album on YouTube Music: {e}"

        if not results:
            return False, f"Album '{search_query}' not found on YouTube Music"

        browse_id = results[0].get('browseId')
        if not browse_id:
            return False, f"Invalid album metadata found for '{search_query}'"

        try:
            album_data = yt.get_album(browse_id)
        except Exception as e:
            logger.error(f"Error fetching album {browse_id}: {e}")
            return False, f"Error fetching album details: {e}"

        tracks = album_data.get('tracks', [])
        if not tracks:
            return False, f"No tracks found in album '{album_data.get('title', search_query)}'"

        album_title = album_data.get('title') or search_query
        album_artists = album_data.get('artists', [])
        primary_artist = album_artists[0]['name'] if album_artists else get_primary_artist(clean_q)
        year = str(album_data.get('year', ''))

        target_folder = "Cravings" if is_craving else "Permanent"
        is_perm = 0 if is_craving else 1

        cursor = conn.cursor()
        queued_count = 0
        track_idx = 1

        for t in tracks:
            vid = t.get('videoId')
            if not vid:
                continue
            t_title = t.get('title', 'Unknown Title')
            t_artists = t.get('artists', [])
            t_artist = ", ".join([a['name'] for a in t_artists if 'name' in a]) if t_artists else primary_artist
            t_dur = t.get('duration_seconds') or 0
            t_num = t.get('trackNumber') or track_idx
            track_idx += 1

            safe_title = sanitize_filename(t_title)
            safe_artist = sanitize_filename(primary_artist)
            safe_album = sanitize_filename(album_title)

            if is_craving:
                f_path = self.paths.get_craving_track_path(safe_artist, safe_album, safe_title)
            else:
                f_path = self.paths.get_permanente_track_path(safe_artist, safe_album, safe_title)

            cursor.execute("SELECT status FROM tracks WHERE id = ?", (vid,))
            existing = cursor.fetchone()
            if existing:
                if existing[0] in ('ARCHIVED', 'PURGED'):
                    cursor.execute("""
                        UPDATE tracks 
                        SET status = 'PENDING', file_path = ?, is_permanent = ?, album = ?, track_number = ?, release_date = ?
                        WHERE id = ?
                    """, (f_path, is_perm, album_title, t_num, year, vid))
                    queued_count += 1
                elif existing[0] == 'CINTA' and not is_craving:
                    cursor.execute("""
                        UPDATE tracks
                        SET status = 'PENDING', file_path = ?, is_permanent = 1, album = ?, track_number = ?, release_date = ?
                        WHERE id = ?
                    """, (f_path, album_title, t_num, year, vid))
                    queued_count += 1
            else:
                cursor.execute("""
                    INSERT INTO tracks (id, title, artist, album, duration_seconds, status, is_permanent, file_path, track_number, release_date)
                    VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?)
                """, (vid, t_title, t_artist, album_title, t_dur, is_perm, f_path, t_num, year))
                queued_count += 1

        conn.commit()
        send_notification("Album Queued", f"{primary_artist} - {album_title}\n{queued_count}/{len(tracks)} tracks queued to {target_folder}")
        return True, f"Album '{primary_artist} - {album_title}' ({queued_count}/{len(tracks)} tracks) queued to {target_folder}"

    def download_single_track(self, conn, query: str, is_craving: bool = False) -> tuple[bool, str]:
        """
        Directly queues a single track to Cravings or Permanent without requiring AI recommendation.
        """
        from ytmusicapi import YTMusic
        yt = self.curator.yt if (self.curator and hasattr(self.curator, 'yt')) else YTMusic()

        clean_q = query.strip().strip('"\'')
        artist = ""
        title = ""
        if " - " in clean_q:
            parts = clean_q.split(" - ", 1)
            artist, title = parts[0].strip(), parts[1].strip()
        elif re.search(r'\s+(?:by|de)\s+', clean_q, re.IGNORECASE):
            parts = re.split(r'\s+(?:by|de)\s+', clean_q, flags=re.IGNORECASE)
            title, artist = parts[0].strip(), parts[1].strip()
        else:
            title = clean_q

        resolved = resolve_album_track(yt, artist, title)
        vid = resolved.get('id')
        if not vid:
            return False, f"Track '{clean_q}' not found on YouTube Music"

        r_title = resolved['title']
        r_artist = resolved['artist']
        r_primary = resolved.get('primary_artist', r_artist)
        r_album = resolved.get('album') or "Singles"
        r_dur = resolved.get('duration_seconds', 0)
        r_track_num = resolved.get('track_number')
        r_rel_date = resolved.get('release_date')

        safe_title = sanitize_filename(r_title)
        safe_artist = sanitize_filename(r_primary)
        safe_album = sanitize_filename(r_album)

        is_perm = 0 if is_craving else 1
        if is_craving:
            f_path = self.paths.get_craving_track_path(safe_artist, safe_album, safe_title)
        else:
            f_path = self.paths.get_permanente_track_path(safe_artist, safe_album, safe_title)

        cursor = conn.cursor()
        cursor.execute("SELECT status, file_path FROM tracks WHERE id = ?", (vid,))
        row = cursor.fetchone()
        if row:
            curr_status = row[0]
            if curr_status in ('ARCHIVED', 'PURGED'):
                cursor.execute("""
                    UPDATE tracks 
                    SET status = 'PENDING', file_path = ?, is_permanent = ?, album = ?, track_number = ?, release_date = ?
                    WHERE id = ?
                """, (f_path, is_perm, r_album, r_track_num, r_rel_date, vid))
            elif curr_status == 'CINTA' and not is_craving:
                cursor.execute("""
                    UPDATE tracks 
                    SET status = 'PENDING', file_path = ?, is_permanent = 1, album = ?, track_number = ?, release_date = ?
                    WHERE id = ?
                """, (f_path, r_album, r_track_num, r_rel_date, vid))
            else:
                dest = "Cravings" if is_craving else "Permanent"
                return True, f"'{r_artist} - {r_title}' already exists in library (status: {curr_status})"
        else:
            cursor.execute("""
                INSERT INTO tracks (id, title, artist, album, duration_seconds, status, is_permanent, file_path, track_number, release_date)
                VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?)
            """, (vid, r_title, r_artist, r_album, r_dur, is_perm, f_path, r_track_num, r_rel_date))

        conn.commit()
        dest = "Cravings" if is_craving else "Permanent"
        send_notification("Track Queued", f"{r_artist} - {r_title}\nQueued to {dest}")
        return True, f"'{r_artist} - {r_title}' queued to {dest}"


    def process_fix_track(self, conn, fix_query: str) -> tuple[bool, str]:
        """
        Repairs a questionable track by searching for its official studio version
        or substituting it with a manually provided YouTube / YT Music URL.
        Syntax:
          fix: <Track> -> <URL>
          reparar: <Track>
        """
        clean_fix = fix_query.strip().strip('"\'')
        target_track = clean_fix
        target_url = None

        if re.search(r'\s*(?:->|=>|=)\s*', clean_fix):
            parts = re.split(r'\s*(?:->|=>|=)\s*', clean_fix, maxsplit=1)
            target_track = parts[0].strip()
            target_url = parts[1].strip()

        cursor = conn.cursor()
        cursor.execute("SELECT id, artist, title, file_path, album FROM tracks WHERE file_path IS NOT NULL")
        all_tracks = cursor.fetchall()
        cand_for_match = [(c[0], c[1], c[2]) for c in all_tracks]
        best_cand, best_score = self._find_best_track_match(cand_for_match, target_track, min_score=70)

        if not best_cand:
            return False, f"Track '{target_track}' not found in library to repair"

        cand_map = {c[0]: c for c in all_tracks}
        c_id, c_artist, c_title, c_fpath, c_album = cand_map[best_cand[0]]

        # Branch 1: Manual replacement URL provided
        if target_url:
            url_info = extract_url_info(target_url)
            manual_vid = url_info.get('id') if (url_info and url_info.get('type') == 'video') else None
            if not manual_vid:
                return False, f"Invalid manual YouTube video URL: '{target_url}'"

            # Remove existing physical audio and lyrics
            if c_fpath and os.path.exists(c_fpath):
                try:
                    os.remove(c_fpath)
                except Exception:
                    pass
                old_lrc = os.path.splitext(c_fpath)[0] + ".lrc"
                if os.path.exists(old_lrc):
                    try:
                        os.remove(old_lrc)
                    except Exception:
                        pass

            _remove_from_download_archive(c_id)
            _remove_from_download_archive(manual_vid)

            cursor.execute("SELECT id FROM tracks WHERE id = ?", (manual_vid,))
            existing_target = cursor.fetchone()
            if existing_target:
                cursor.execute("DELETE FROM tracks WHERE id = ?", (c_id,))
                cursor.execute("UPDATE tracks SET status = 'PENDING', file_path = ? WHERE id = ?", (c_fpath, manual_vid))
            else:
                cursor.execute("UPDATE tracks SET id = ?, status = 'PENDING' WHERE id = ?", (manual_vid, c_id))

            conn.commit()
            logger.info(f"Track repaired via manual URL: '{c_artist} - {c_title}' -> ID: {manual_vid}")
            send_notification("Track Repaired", f"{c_artist} - {c_title}\nAudio replaced from provided URL")
            return True, f"'{c_artist} - {c_title}' audio replaced with manual URL (ID: {manual_vid})"

        # Branch 2: Automatic studio repair
        if not self.curator:
            from ytmusicapi import YTMusic
            yt = YTMusic()
            client = None
            model_name = "gemini-3.5-flash"
        else:
            yt = self.curator.yt
            client = self.curator.client
            model_name = self.curator.model_name

        fixed = auto_fix_track(yt, c_artist, c_title, current_vid=c_id, client=client, model_name=model_name)
        if fixed.get('fixed') and fixed.get('id') != c_id:
            new_id = fixed['id']
            if c_fpath and os.path.exists(c_fpath):
                try:
                    os.remove(c_fpath)
                except Exception:
                    pass
                old_lrc = os.path.splitext(c_fpath)[0] + ".lrc"
                if os.path.exists(old_lrc):
                    try:
                        os.remove(old_lrc)
                    except Exception:
                        pass

            _remove_from_download_archive(c_id)
            _remove_from_download_archive(new_id)

            cursor.execute("SELECT id FROM tracks WHERE id = ?", (new_id,))
            if cursor.fetchone():
                cursor.execute("DELETE FROM tracks WHERE id = ?", (c_id,))
                cursor.execute("UPDATE tracks SET status = 'PENDING', file_path = ? WHERE id = ?", (c_fpath, new_id))
            else:
                cursor.execute("UPDATE tracks SET id = ?, status = 'PENDING' WHERE id = ?", (new_id, c_id))

            conn.commit()
            logger.info(f"Track auto-repaired: '{c_artist} - {c_title}' -> New ID: {new_id}")
            send_notification("Track Repaired", f"{c_artist} - {c_title}\nOfficial version will be downloaded")
            return True, f"'{c_artist} - {c_title}' repaired to new ID: {new_id}"
        else:
            return False, f"No alternative official version found automatically. Use manual URL: fix: {c_artist} - {c_title} -> https://music.youtube.com/watch?v=..."

    def clean_peticiones_file(self, peticiones_path: str, header_lines: list[str], failed_lines: list[str] = None, info_lines: list[str] = None):
        """Restores requests mailbox header clearing only successful orders and reporting failures and info results."""
        try:
            with open(peticiones_path, 'w', encoding='utf-8') as f:
                if header_lines:
                    for hl in header_lines:
                        f.write(hl if hl.endswith('\n') else hl + '\n')
                else:
                    target_header = get_mailbox_header(self.paths.language)
                    f.write(target_header if target_header.endswith('\n') else target_header + '\n')

                if info_lines:
                    info_title = (
                        "\n# --- INFORMACIÓN DE PISTAS (Resultados) ---\n"
                        if self.paths.language == "es"
                        else "\n# --- TRACK INFORMATION (Results) ---\n"
                    )
                    f.write(info_title)
                    for il in info_lines:
                        f.write(il if il.endswith('\n') else il + '\n')

                if failed_lines:
                    uncompleted_title = (
                        "\n# --- ÓRDENES NO COMPLETADAS (Ver detalles abajo) ---\n"
                        if self.paths.language == "es"
                        else "\n# --- UNCOMPLETED ORDERS (See details below) ---\n"
                    )
                    f.write(uncompleted_title)
                    for fl in failed_lines:
                        f.write(fl if fl.endswith('\n') else fl + '\n')
        except Exception as e:
            logger.error(f"Error restoring header of requests mailbox: {e}")

    def process_peticiones(self, conn=None) -> int:
        """
        Reads and processes all orders and requests in peticiones.txt.
        Returns the number of processed orders.
        """
        peticiones_path = self.paths.peticiones_file
        if not os.path.exists(peticiones_path):
            return 0

        try:
            with open(peticiones_path, 'r', encoding='utf-8') as f:
                raw_lines = f.readlines()
        except Exception as e:
            logger.error(f"Error reading requests file: {e}")
            return 0

        header_lines = []
        user_lines = []
        in_header = True
        for rl in raw_lines:
            s_line = rl.strip()
            if in_header:
                if s_line.startswith('#') or s_line == '':
                    header_lines.append(rl)
                else:
                    in_header = False
                    user_lines.append(s_line)
            else:
                if s_line and not s_line.startswith('#'):
                    user_lines.append(s_line)

        if not user_lines:
            return 0

        # Manage DB connection if not provided
        close_conn = False
        if conn is None:
            conn = get_db_connection(self.db_path)
            close_conn = True

        remaining_lines = []
        failed_commands = []
        info_lines = []
        processed_orders = 0

        try:
            for line in user_lines:
                processed_orders += 1

                # 1. Track Inspection / Query Info
                if re.match(r'^(?:info|informacion|información|information):\s*', line, re.IGNORECASE):
                    payload = re.sub(r'^(?:info|informacion|información|information):\s*', '', line, flags=re.IGNORECASE).strip()
                    ok, msg = self.process_info_track(conn, payload)
                    if ok:
                        info_lines.append(f"# {msg}")
                    else:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                # 2. Permanent Purge (explicit command for permanent items)
                elif re.match(r'^(?:purge\s+permanent|borrar\s+permanente|eliminar\s+permanente|delete\s+permanent|remove\s+permanent|quitar\s+permanente):\s*', line, re.IGNORECASE):
                    payload = re.sub(r'^(?:purge\s+permanent|borrar\s+permanente|eliminar\s+permanente|delete\s+permanent|remove\s+permanent|quitar\s+permanente):\s*', '', line, flags=re.IGNORECASE).strip()
                    ok, msg = self.process_purge_permanent(conn, payload)
                    if not ok:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                # 3. Repair Command (Auto or Manual YT URL)
                elif line.lower().startswith(('fix:', 'repair:', 'reparar:', 'arreglar:')):
                    fix_query = re.sub(r'^(fix|repair|reparar|arreglar):\s*', '', line, flags=re.IGNORECASE).strip()
                    logger.info(f"Repair command received: '{fix_query}'")
                    ok, msg = self.process_fix_track(conn, fix_query)
                    if not ok:
                        failed_commands.append(f"{line}  # NOTICE: {msg}")

                # 4. Force Re-download Track
                elif re.match(r'^(?:redownload|redescargar|re-descargar|volver\s+a\s+descargar):\s*', line, re.IGNORECASE):
                    payload = re.sub(r'^(?:redownload|redescargar|re-descargar|volver\s+a\s+descargar):\s*', '', line, flags=re.IGNORECASE).strip()
                    ok, msg = self.process_redownload_track(conn, payload)
                    if not ok:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                # 5. Reassign Primary Artist
                elif re.match(r'^(?:artist|artista):\s*', line, re.IGNORECASE):
                    payload = re.sub(r'^(?:artist|artista):\s*', '', line, flags=re.IGNORECASE).strip()
                    if re.search(r'\s*(?:->|=>|=)\s*', payload):
                        parts = re.split(r'\s*(?:->|=>|=)\s*', payload, maxsplit=1)
                        ok, msg = self.process_artist_move(conn, parts[0], parts[1])
                        if not ok:
                            failed_commands.append(f"{line}  # ERROR: {msg}")
                    else:
                        failed_commands.append(f"{line}  # ERROR: Missing arrow (Syntax: artist: <Track> -> <New Artist>)")

                # 6. Personal Playlists Management ('playlist: Gym += Track' or 'lista: Gym -= Track')
                elif re.match(r'^(?:playlist|lista):\s*(.+?)\s*(\+=|-=)\s*(.+)$', line, re.IGNORECASE):
                    pl_m = re.match(r'^(?:playlist|lista):\s*(.+?)\s*(\+=|-=)\s*(.+)$', line, re.IGNORECASE)
                    pl_name = pl_m.group(1).strip()
                    op = pl_m.group(2).strip()
                    s_query = pl_m.group(3).strip()
                    ok, msg = self.process_playlist_command(conn, pl_name, op, s_query)
                    if not ok:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                # 7. Direct URL (YouTube, YouTube Music, or Spotify)
                elif re.match(r'^(?:url|link|enlace):\s*(https?://\S+)', line, re.IGNORECASE):
                    raw_url = re.sub(r'^(?:url|link|enlace):\s*', '', line, flags=re.IGNORECASE).strip()
                    is_crav = bool(re.search(r'\b(?:craving|antojo)\b', line, re.IGNORECASE))
                    ok, msg = self.process_direct_url(conn, raw_url, is_craving=is_crav)
                    if not ok:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                elif re.match(r'^https?://\S+', line, re.IGNORECASE):
                    raw_url = line.strip()
                    ok, msg = self.process_direct_url(conn, raw_url, is_craving=False)
                    if not ok:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                elif re.match(r'^(?:craving|antojo):\s*(https?://\S+)', line, re.IGNORECASE):
                    raw_url = re.sub(r'^(?:craving|antojo):\s*', '', line, flags=re.IGNORECASE).strip()
                    ok, msg = self.process_direct_url(conn, raw_url, is_craving=True)
                    if not ok:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                elif re.match(r'^(?:permanent|permanente):\s*(https?://\S+)', line, re.IGNORECASE):
                    raw_url = re.sub(r'^(?:permanent|permanente):\s*', '', line, flags=re.IGNORECASE).strip()
                    ok, msg = self.process_direct_url(conn, raw_url, is_craving=False)
                    if not ok:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                # 8. Craving Album Download
                elif re.match(r'^(?:craving\s+album|antojo\s+album|album\s+craving|album\s+antojo):\s*', line, re.IGNORECASE):
                    payload = re.sub(r'^(?:craving\s+album|antojo\s+album|album\s+craving|album\s+antojo):\s*', '', line, flags=re.IGNORECASE).strip()
                    ok, msg = self.download_album(conn, payload, is_craving=True)
                    if not ok:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                # 9. Permanent Album Download
                elif re.match(r'^(?:permanent\s+album|permanente\s+album|album\s+permanent|album\s+permanente):\s*', line, re.IGNORECASE):
                    payload = re.sub(r'^(?:permanent\s+album|permanente\s+album|album\s+permanent|album\s+permanente):\s*', '', line, flags=re.IGNORECASE).strip()
                    ok, msg = self.download_album(conn, payload, is_craving=False)
                    if not ok:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                # 10. Album reassignment ('album: <song> -> <new album>') OR Permanent Album Download ('album: <artist> - <album>')
                elif re.match(r'^(?:album|disco):\s*', line, re.IGNORECASE):
                    payload = re.sub(r'^(?:album|disco):\s*', '', line, flags=re.IGNORECASE).strip()
                    if re.search(r'\s*(?:->|=>|=)\s*', payload):
                        parts = re.split(r'\s*(?:->|=>|=)\s*', payload, maxsplit=1)
                        ok, msg = self.process_album_move(conn, parts[0], parts[1])
                        if not ok:
                            failed_commands.append(f"{line}  # ERROR: {msg}")
                    else:
                        ok, msg = self.download_album(conn, payload, is_craving=False)
                        if not ok:
                            failed_commands.append(f"{line}  # ERROR: {msg}")

                # 10.b Natural language album download: 'Download album "X" by "Y"'
                elif re.match(r'^(?:download|descargar)\s+(?:the\s+album|el\s+album|el\s+álbum|el\s+disco|album|álbum|disco)\s+(.+)', line, re.IGNORECASE):
                    payload = re.sub(r'^(?:download|descargar)\s+(?:the\s+album|el\s+album|el\s+álbum|el\s+disco|album|álbum|disco)\s+', '', line, flags=re.IGNORECASE).strip()
                    is_craving_req = bool(re.search(r'\b(?:craving|antojo)\b', line, re.IGNORECASE))
                    payload = re.sub(r'\b(?:as\s+craving|como\s+antojo|craving|antojo|permanent|permanente)\b', '', payload, flags=re.IGNORECASE).strip()
                    ok, msg = self.download_album(conn, payload, is_craving=is_craving_req)
                    if not ok:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                # 10.c Natural language album move: 'Move songs "X" and "Y" to album "Z"'
                elif re.search(r'(?:move|transfer|assign|mueve|cambia|pon|traslada|mover)\s+(?:the\s+song|the\s+songs|tracks|songs|la canción|las canciones|los temas|el tema)?\s*(.+?)\s*(?:from\s+[^t]+|de\s+[^a]+)?\s*(?:to\s+album|al\s+álbum)\s*["\'\*]?([^"\'\*\.]+)', line, re.IGNORECASE):
                    nl_m = re.search(r'(?:move|transfer|assign|mueve|cambia|pon|traslada|mover)\s+(?:the\s+song|the\s+songs|tracks|songs|la canción|las canciones|los temas|el tema)?\s*(.+?)\s*(?:from\s+[^t]+|de\s+[^a]+)?\s*(?:to\s+album|al\s+álbum)\s*["\'\*]?([^"\'\*\.]+)', line, re.IGNORECASE)
                    songs_part = nl_m.group(1).strip()
                    album_target = nl_m.group(2).strip()
                    quotes = re.findall(r'["“](.+?)["”]', songs_part)
                    target_songs = quotes if quotes else [s.strip() for s in re.split(r'\s*(?:,| and | y | e )\s*', songs_part) if s.strip()]
                    for s in target_songs:
                        ok, msg = self.process_album_move(conn, s, album_target)
                        if not ok:
                            failed_commands.append(f'album: {s} -> {album_target}  # ERROR: {msg}')

                # 11. Single Track Craving Download
                elif re.match(r'^(?:craving|antojo):\s*', line, re.IGNORECASE):
                    payload = re.sub(r'^(?:craving|antojo):\s*', '', line, flags=re.IGNORECASE).strip()
                    ok, msg = self.download_single_track(conn, payload, is_craving=True)
                    if not ok:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                # 11.b Natural language craving track download
                elif re.match(r'^(?:download|descargar)\s+(?:the\s+craving|el\s+antojo|craving|antojo)\s+(.+)', line, re.IGNORECASE):
                    payload = re.sub(r'^(?:download|descargar)\s+(?:the\s+craving|el\s+antojo|craving|antojo)\s+', '', line, flags=re.IGNORECASE).strip()
                    ok, msg = self.download_single_track(conn, payload, is_craving=True)
                    if not ok:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                # 12. Local Radio Command
                elif line.lower().startswith('radio:'):
                    vibra = line[6:].strip()
                    logger.info(f"Local Radio mode activated for: '{vibra}'")
                    if self.curator:
                        self.curator.generate_local_radio(vibra)
                    send_notification("Local Radio Generated", f"Vibe: {vibra}")

                # 13. Music Genre Correction / Assignment
                elif re.match(r'^(?:genre|genero|género):\s*', line, re.IGNORECASE):
                    payload = re.sub(r'^(?:genre|genero|género):\s*', '', line, flags=re.IGNORECASE).strip()
                    if re.search(r'\s*(?:->|=>|=)\s*', payload):
                        parts = re.split(r'\s*(?:->|=>|=)\s*', payload, maxsplit=1)
                        ok, msg = self.process_genre_update(conn, parts[0], parts[1])
                    else:
                        ok, msg = self.process_genre_update(conn, payload, None)
                    if not ok:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                # 13.b Natural language genre phrase: 'Change genre of "X" to "Y"'
                elif re.search(r'(?:change|set|fix|update|cambia|pon|corrige|actualiza)\s+(?:the\s+)?(?:genre|g[ée]nero)\s+(?:of|for|de)\s+["\']?([^"\']+)["\']?\s+(?:to|a)\s+["\']?([^"\']+)["\']?', line, re.IGNORECASE):
                    gm = re.search(r'(?:change|set|fix|update|cambia|pon|corrige|actualiza)\s+(?:the\s+)?(?:genre|g[ée]nero)\s+(?:of|for|de)\s+["\']?([^"\']+)["\']?\s+(?:to|a)\s+["\']?([^"\']+)["\']?', line, re.IGNORECASE)
                    ok, msg = self.process_genre_update(conn, gm.group(1), gm.group(2))
                    if not ok:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                # 14. Lyrics Update / Upgrade
                elif re.match(r'^(?:lyrics|lyric|letra):\s*', line, re.IGNORECASE):
                    payload = re.sub(r'^(?:lyrics|lyric|letra):\s*', '', line, flags=re.IGNORECASE).strip()
                    ok, msg = self.process_lyrics_update(conn, payload)
                    if not ok:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                # 15. Permanent Track Request / Promotion
                elif re.match(r'^(?:permanent|permanente):\s*', line, re.IGNORECASE):
                    payload = re.sub(r'^(?:permanent|permanente):\s*', '', line, flags=re.IGNORECASE).strip()
                    # Try promoting from Conveyor/Cravings first
                    ok, msg = self.process_promote_track(conn, payload)
                    if not ok:
                        # Otherwise download new track directly to Permanent
                        ok, msg = self.download_single_track(conn, payload, is_craving=False)
                    if not ok:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                # 15.b Promote / Shield to Permanent
                elif re.match(r'^(?:favorite|fav|promote|shield|save|favorita|favorito|guardar|blindar):\s*', line, re.IGNORECASE):
                    payload = re.sub(r'^(?:favorite|fav|promote|shield|save|favorita|favorito|guardar|blindar):\s*', '', line, flags=re.IGNORECASE).strip()
                    ok, msg = self.process_promote_track(conn, payload)
                    if not ok:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                # 16. Purge / Delete from Conveyor or Cravings
                elif re.match(r'^(?:purge|delete|remove|borrar|eliminar|quitar):\s*', line, re.IGNORECASE):
                    payload = re.sub(r'^(?:purge|delete|remove|borrar|eliminar|quitar):\s*', '', line, flags=re.IGNORECASE).strip()
                    ok, msg = self.process_purge_track(conn, payload)
                    if not ok:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                else:
                    remaining_lines.append(line)

            # Music requests sent to LLM Curator
            if remaining_lines and self.curator:
                combined_text = "\n".join(remaining_lines)
                logger.info(f"Requests mailbox: Processing musical intent: '{combined_text[:60]}...'")
                intent_groups = self.curator.run_intent_curation(combined_text)
                if intent_groups is not None:
                    val_intent = 0
                    for group in intent_groups:
                        val_intent += self.curator.validate_and_save(group.tracks, target_folder="Permanente", target_status="PENDING")
                    logger.info(f"Requested tracks validated and inserted into Permanent: {val_intent}")

                    if val_intent == 0 and intent_groups:
                        for group in intent_groups:
                            for t in group.tracks:
                                failed_commands.append(f'Download "{t.title}" by {t.artist}  # NOTICE: Already exists in your permanent collection')
                    elif val_intent == 0 and not intent_groups:
                        for rl in remaining_lines:
                            failed_commands.append(f'{rl}  # ERROR: No results could be found for this request')

                    self.clean_peticiones_file(peticiones_path, header_lines, failed_commands, info_lines=info_lines)
                else:
                    logger.warning("Requests mailbox file was not cleared due to temporary Gemini error.")
                    for rl in remaining_lines:
                        failed_commands.append(f'{rl}  # ERROR: Temporary error connecting to Gemini (quota or network)')
                    self.clean_peticiones_file(peticiones_path, header_lines, failed_commands, info_lines=info_lines)
            else:
                self.clean_peticiones_file(peticiones_path, header_lines, failed_commands, info_lines=info_lines)

        finally:
            if close_conn and conn:
                conn.close()

        return processed_orders
