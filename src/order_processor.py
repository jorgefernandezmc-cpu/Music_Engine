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
from thefuzz import fuzz
from mutagen.oggopus import OggOpus
from mutagen.mp4 import MP4

from src.db import get_db_connection
from src.paths import StoragePaths
from src.notifications import send_notification
from src.album_resolver import get_primary_artist, auto_fix_track
from src.genre_resolver import clean_genre_string, apply_genre_metadata, resolve_genre
from src.enrich_lyrics import check_and_upgrade_track

logger = logging.getLogger('order_processor')

DEFAULT_PETICIONES_HEADER = """# ==============================================================================
#                      REMOTE REQUESTS AND COMMANDS MAILBOX
# ==============================================================================
# Write your requests or commands at the bottom of this file (one per line).
# This header is always retained; only completed orders will be cleared.
# If any order cannot be completed, the reason will be reported right here.
#
# 1. REQUEST NEW MUSIC OR DISCOVERIES (AI + Official Catalog to Permanent):
#    - A song:   Download "Song Title" by Artist
#    - An artist: Duki
#    - A genre:   Melodic techno for workouts / Indie pop
#
# 2. FIX OR ASSIGN MUSIC GENRE (SQLite + Physical metadata):
#    genre: <Song> -> <New Genre>
#    Example:  genre: So Payaso -> Hard Rock / Rock
#    (Or leave without arrow to re-analyze and auto-correct:  genre: Neverita)
#
# 3. UPDATE OR UPGRADE LYRICS (Fresh real-time synced .lrc download):
#    lyrics: <Song>
#    Example:  lyrics: Bohemian Rhapsody
#
# 4. SHIELD / PROMOTE SONG TO PERMANENT (Moves from Conveyor to Permanent immediately):
#    favorite: <Song>
#    Example:  favorite: Cuica
#
# 5. REMOVE / PURGE SONG FROM CONVEYOR (Physical deletion of audio and .lrc):
#    purge: <Song>
#    Example:  purge: Song I Dislike
#
# 6. MOVE OR ASSIGN SONG TO OFFICIAL ALBUM (0% AI, 100% exact):
#    album: <Song> -> <Album Name>
#    Example:  album: NO PIENSO LLAMAR -> STORM
#
# 7. REPAIR QUESTIONABLE TRACK / AUDIT OFFICIAL VERSION:
#    fix: <Song Name>
#    Example:  fix: Me Enamoraste
#
# 8. CREATE INSTANT LOCAL RADIO (from your existing offline collection):
#    radio: <Vibe or Mood>
#    Example:  radio: Acoustic chill
# ==============================================================================
# WRITE YOUR REQUESTS BELOW:
"""

DEFAULT_ANTOJOS_HEADER = DEFAULT_PETICIONES_HEADER


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
        1. O(1) exact equality check for title or artist - title.
        2. Fuzzy matching with token_set_ratio.
        """
        clean_q = query.strip().strip('"\'').lower()
        if not clean_q or not tracks:
            return None, 0

        # Step 1: Exact quick shortcut
        for cand in tracks:
            c_art = str(cand[1] or "").lower()
            c_tit = str(cand[2] or "").lower()
            if clean_q == c_tit or clean_q == f"{c_art} {c_tit}" or clean_q == f"{c_art} - {c_tit}":
                return cand, 100

        # Step 2: Fuzzy search
        best_cand = None
        best_score = 0
        for cand in tracks:
            c_art = str(cand[1] or "").lower()
            c_tit = str(cand[2] or "").lower()
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
        Immediately promotes a song from Conveyor to Permanent, moving it to artist/album folder.
        """
        clean_q = song_query.strip().strip('"\'')
        cursor = conn.cursor()
        cursor.execute("SELECT id, artist, title, album, file_path FROM tracks WHERE status = 'CINTA'")
        cinta_tracks = cursor.fetchall()

        best_cand, best_score = self._find_best_track_match(cinta_tracks, clean_q, min_score=75)
        if not best_cand:
            return False, f"Track '{clean_q}' not found in Conveyor"

        t_id, t_art, t_tit, t_alb, t_fpath = best_cand
        p_artist = get_primary_artist(t_art)
        ext = os.path.splitext(t_fpath)[1] if t_fpath else '.opus'
        clean_alb = t_alb if t_alb else "Singles"
        new_path = self.paths.get_permanente_track_path(p_artist, clean_alb, t_tit, ext=ext)
        os.makedirs(os.path.dirname(new_path), exist_ok=True)

        if t_fpath and os.path.exists(t_fpath):
            shutil.move(t_fpath, new_path)
            old_lrc = os.path.splitext(t_fpath)[0] + ".lrc"
            new_lrc = os.path.splitext(new_path)[0] + ".lrc"
            if os.path.exists(old_lrc):
                shutil.move(old_lrc, new_lrc)

        cursor.execute("UPDATE tracks SET status = 'PERMANENT', is_permanent = 1, file_path = ? WHERE id = ?", (new_path, t_id))
        conn.commit()
        send_notification("Shielded in Permanent", f"{t_art} - {t_tit}\nMoved to Permanent/{p_artist}/{clean_alb}")
        if self.playlists:
            self.playlists.update_all_playlists()
        return True, f"'{t_art} - {t_tit}' promoted to Permanent"

    def process_purge_track(self, conn, song_query: str) -> tuple[bool, str]:
        """
        Immediately purges a track from Conveyor and marks it as PURGED to prevent re-downloads.
        """
        clean_q = song_query.strip().strip('"\'')
        cursor = conn.cursor()
        cursor.execute("SELECT id, artist, title, file_path FROM tracks WHERE status = 'CINTA'")
        cinta_tracks = cursor.fetchall()

        best_cand, best_score = self._find_best_track_match(cinta_tracks, clean_q, min_score=75)
        if not best_cand:
            return False, f"Track '{clean_q}' not found in Conveyor"

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

        cursor.execute("UPDATE tracks SET status = 'PURGED' WHERE id = ?", (t_id,))
        conn.commit()
        send_notification("Track Purged", f"{t_art} - {t_tit}\nRemoved from Conveyor")
        if self.playlists:
            self.playlists.update_cinta_playlists()
        return True, f"'{t_art} - {t_tit}' purged from Conveyor"

    def process_fix_track(self, conn, fix_query: str) -> tuple[bool, str]:
        """
        Repairs a questionable track by searching for its official studio version.
        """
        if not self.curator:
            return False, "Curator not available to repair track"

        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, artist, title, file_path, album FROM tracks WHERE LOWER(title) LIKE LOWER(?) OR LOWER(artist) LIKE LOWER(?)",
            (f"%{fix_query}%", f"%{fix_query}%")
        )
        cand = cursor.fetchone()
        if not cand:
            return False, "Track not found in library to repair"

        c_id, c_artist, c_title, c_fpath, c_album = cand
        fixed = auto_fix_track(self.curator.yt, c_artist, c_title, current_vid=c_id, client=self.curator.client, model_name=self.curator.model_name)
        if fixed.get('fixed') and fixed.get('id') != c_id:
            new_id = fixed['id']
            cursor.execute("SELECT id FROM tracks WHERE id = ?", (new_id,))
            if cursor.fetchone():
                cursor.execute("DELETE FROM tracks WHERE id = ?", (c_id,))
            else:
                cursor.execute("UPDATE tracks SET id = ?, status = 'PENDING' WHERE id = ?", (new_id, c_id))

            if c_fpath and os.path.exists(c_fpath):
                try:
                    os.remove(c_fpath)
                    old_lrc = os.path.splitext(c_fpath)[0] + ".lrc"
                    if os.path.exists(old_lrc):
                        os.remove(old_lrc)
                except Exception:
                    pass

            conn.commit()
            logger.info(f"Track repaired: '{c_artist} - {c_title}' -> New ID: {new_id}")
            send_notification("Track Repaired", f"{c_artist} - {c_title}\nOfficial version will be downloaded")
            return True, f"'{c_artist} - {c_title}' repaired to new ID: {new_id}"
        else:
            return False, "Already had the most official version found"

    def clean_peticiones_file(self, peticiones_path: str, header_lines: list[str], failed_lines: list[str] = None):
        """Restores requests mailbox header clearing only successful orders and reporting failures."""
        try:
            with open(peticiones_path, 'w', encoding='utf-8') as f:
                if header_lines:
                    for hl in header_lines:
                        f.write(hl if hl.endswith('\n') else hl + '\n')
                else:
                    f.write(DEFAULT_PETICIONES_HEADER + '\n')

                if failed_lines:
                    f.write("\n# --- UNCOMPLETED ORDERS (See details below) ---\n")
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
        processed_orders = 0

        try:
            for line in user_lines:
                processed_orders += 1

                # 1. Album reassignment: 'album: <song> -> <new album>'
                if re.match(r'^(?:album|disco):\s*', line, re.IGNORECASE):
                    payload = re.sub(r'^(?:album|disco):\s*', '', line, flags=re.IGNORECASE).strip()
                    parts = re.split(r'\s*(?:->|=>|=)\s*', payload, maxsplit=1)
                    if len(parts) == 2:
                        ok, msg = self.process_album_move(conn, parts[0], parts[1])
                        if not ok:
                            failed_commands.append(f"{line}  # ERROR: {msg}")
                    else:
                        logger.warning(f"Invalid syntax in album command: '{line}'")
                        failed_commands.append(f"{line}  # ERROR: Invalid syntax. Use: album: Song -> New Album")

                # 1.b Natural language album phrase: 'Move songs "X" and "Y" to album "Z"'
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

                # 2. Local Radio Command
                elif line.lower().startswith('radio:'):
                    vibra = line[6:].strip()
                    logger.info(f"Local Radio mode activated for: '{vibra}'")
                    if self.curator:
                        self.curator.generate_local_radio(vibra)
                    send_notification("Local Radio Generated", f"Vibe: {vibra}")

                # 3. Repair Command
                elif line.lower().startswith(('fix:', 'repair:', 'reparar:', 'arreglar:')):
                    fix_query = re.sub(r'^(fix|repair|reparar|arreglar):\s*', '', line, flags=re.IGNORECASE).strip()
                    logger.info(f"Repair command received: '{fix_query}'")
                    ok, msg = self.process_fix_track(conn, fix_query)
                    if not ok:
                        failed_commands.append(f"{line}  # NOTICE: {msg}")

                # 4. Music Genre Correction / Assignment
                elif re.match(r'^(?:genre|genero|género):\s*', line, re.IGNORECASE):
                    payload = re.sub(r'^(?:genre|genero|género):\s*', '', line, flags=re.IGNORECASE).strip()
                    if re.search(r'\s*(?:->|=>|=)\s*', payload):
                        parts = re.split(r'\s*(?:->|=>|=)\s*', payload, maxsplit=1)
                        ok, msg = self.process_genre_update(conn, parts[0], parts[1])
                    else:
                        ok, msg = self.process_genre_update(conn, payload, None)
                    if not ok:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                # 4.b Natural language genre phrase: 'Change genre of "X" to "Y"'
                elif re.search(r'(?:change|set|fix|update|cambia|pon|corrige|actualiza)\s+(?:the\s+)?(?:genre|g[ée]nero)\s+(?:of|for|de)\s+["\']?([^"\']+)["\']?\s+(?:to|a)\s+["\']?([^"\']+)["\']?', line, re.IGNORECASE):
                    gm = re.search(r'(?:change|set|fix|update|cambia|pon|corrige|actualiza)\s+(?:the\s+)?(?:genre|g[ée]nero)\s+(?:of|for|de)\s+["\']?([^"\']+)["\']?\s+(?:to|a)\s+["\']?([^"\']+)["\']?', line, re.IGNORECASE)
                    ok, msg = self.process_genre_update(conn, gm.group(1), gm.group(2))
                    if not ok:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                # 5. Lyrics Update / Upgrade
                elif re.match(r'^(?:lyrics|lyric|letra):\s*', line, re.IGNORECASE):
                    payload = re.sub(r'^(?:lyrics|lyric|letra):\s*', '', line, flags=re.IGNORECASE).strip()
                    ok, msg = self.process_lyrics_update(conn, payload)
                    if not ok:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                # 6. Promote / Shield to Permanent
                elif re.match(r'^(?:favorite|fav|permanent|promote|shield|save|favorita|favorito|permanente|guardar|blindar):\s*', line, re.IGNORECASE):
                    payload = re.sub(r'^(?:favorite|fav|permanent|promote|shield|save|favorita|favorito|permanente|guardar|blindar):\s*', '', line, flags=re.IGNORECASE).strip()
                    ok, msg = self.process_promote_track(conn, payload)
                    if not ok:
                        failed_commands.append(f"{line}  # ERROR: {msg}")

                # 7. Purge / Delete from Conveyor
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

                    self.clean_peticiones_file(peticiones_path, header_lines, failed_commands)
                else:
                    logger.warning("Requests mailbox file was not cleared due to temporary Gemini error.")
                    for rl in remaining_lines:
                        failed_commands.append(f'{rl}  # ERROR: Temporary error connecting to Gemini (quota or network)')
                    self.clean_peticiones_file(peticiones_path, header_lines, failed_commands)
            else:
                self.clean_peticiones_file(peticiones_path, header_lines, failed_commands)

        finally:
            if close_conn and conn:
                conn.close()

        return processed_orders
