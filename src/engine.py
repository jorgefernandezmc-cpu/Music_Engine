"""
engine.py
Main lifecycle orchestrator for 'The Conveyor Belt' (Music Engine).
Coordinates file synchronization, telemetry, smart curation, downloads, and playlists.
"""

import os
import time
import shutil
import logging
import yaml
from datetime import datetime
from filelock import FileLock, Timeout

from src.paths import StoragePaths
from src.db import get_db_connection
from src.album_resolver import get_primary_artist
from src.telemetry import TelemetryEngine
from src.curator_llm import CuratorLLM, TrackRecommendation
from src.downloader import Downloader
from src.playlist_gen import PlaylistGenerator
from src.sync import FileSyncManager
from src.order_processor import OrderProcessor, DEFAULT_PETICIONES_HEADER, DEFAULT_ANTOJOS_HEADER
from src.notifications import send_notification, set_notification_language
from src.backup_manager import BackupManager

logger = logging.getLogger('engine')
os.makedirs('logs', exist_ok=True)
if not logger.handlers:
    fh = logging.FileHandler('logs/engine.log')
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(fh)
    logger.setLevel(logging.INFO)


class MusicEngine:
    def __init__(self, db_path: str = "data/conveyor_state.sqlite", config_path: str = "config/config.yaml"):
        self.db_path = db_path
        self.config_path = config_path

        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f) or {}

        self.paths = StoragePaths(config_path)
        set_notification_language(self.paths.language)
        self.paths.ensure_dirs()

        # Modular configuration
        self.conveyor_config = self.config.get('conveyor', {})
        self.storage_config = self.config.get('storage', {})
        self.downloader_config = self.config.get('downloader', {})
        self.telemetry_config = self.config.get('telemetry', {})
        self.notif_config = self.config.get('notifications', {})

        # Operational adjustable parameters
        self.max_db_backups = self.storage_config.get('max_db_backups', 5)
        self.curation_batch_per_cycle = self.conveyor_config.get('curation_batch_per_cycle', 20)
        self.max_skips_before_purge = self.conveyor_config.get('max_skips_before_purge', 5)
        self.max_skip_ratio = float(self.conveyor_config.get('max_skip_ratio', 0.7))
        self.cycle_max_downloads = self.downloader_config.get('cycle_max_downloads', 50)
        self.notifications_enabled = self.notif_config.get('enabled', True)

        # Specialized modules
        self.telemetry = TelemetryEngine(db_path, config_path)
        self.curator = CuratorLLM(db_path, config_path)
        self.downloader = Downloader(db_path, config_path)
        self.playlists = PlaylistGenerator(db_path, self.paths)
        self.file_sync = FileSyncManager(db_path, self.paths, self.playlists, self.config)
        self.order_processor = OrderProcessor(db_path, config_path, self.paths, self.playlists, self.curator)
        self.backup_manager = BackupManager(db_path, self.paths)

    def run(self, fill_mode=False):
        """Entry point for execution with exclusive lock (filelock)."""
        os.makedirs('data', exist_ok=True)
        lock_path = "data/engine.lock"
        try:
            with FileLock(lock_path, timeout=1):
                self._run_internal(fill_mode)
        except Timeout:
            logger.warning("Engine currently running in another process. Exiting safely.")

    # --- Methods delegated to FileSyncManager (compatibility and clarity) ---
    def _sync_manual_moves(self) -> int:
        return self.file_sync.sync_manual_moves()

    def _clean_ghost_tracks(self) -> int:
        return self.file_sync.clean_ghost_tracks()

    def _process_local_file_ratings(self) -> int:
        return self.file_sync.process_local_file_ratings()

    # --- Methods delegated to OrderProcessor (compatibility and clarity) ---
    def _process_album_move(self, conn, song_query: str, new_album: str) -> bool:
        ok, _ = self.order_processor.process_album_move(conn, song_query, new_album)
        return ok

    def _process_genre_update(self, conn, song_query: str, new_genre: str = None) -> tuple[bool, str]:
        return self.order_processor.process_genre_update(conn, song_query, new_genre)

    def _process_lyrics_update(self, conn, song_query: str) -> tuple[bool, str]:
        return self.order_processor.process_lyrics_update(conn, song_query)

    def _process_promote_track(self, conn, song_query: str) -> tuple[bool, str]:
        return self.order_processor.process_promote_track(conn, song_query)

    def _process_purge_track(self, conn, song_query: str) -> tuple[bool, str]:
        return self.order_processor.process_purge_track(conn, song_query)

    def _clean_peticiones_file(self, peticiones_path: str, header_lines: list[str], failed_lines: list[str] = None):
        return self.order_processor.clean_peticiones_file(peticiones_path, header_lines, failed_lines)

    _clean_antojos_file = _clean_peticiones_file

    def _purge_cravings(self, cursor) -> int:
        """
        Purges expired temporary tracks from Cravings folder based on retention_days.
        Deletes physical audio files, sidecars, empty directories, and sets status to PURGED.
        """
        cravings_cfg = self.config.get('cravings', {}) or self.config.get('antojos', {})
        retention_days = cravings_cfg.get('retention_days', 30)
        if retention_days <= 0:
            return 0

        cursor.execute("""
            SELECT id, file_path FROM tracks 
            WHERE status = 'ANTOJO' 
            AND (julianday('now') - julianday(COALESCE(last_played_at, added_at))) > ?
        """, (retention_days,))
        to_purge = cursor.fetchall()

        purged_count = 0
        for t_id, f_path in to_purge:
            try:
                old_dir = os.path.dirname(f_path) if f_path else None
                if f_path and os.path.exists(f_path):
                    os.remove(f_path)

                if f_path:
                    base_p = os.path.splitext(f_path)[0]
                    for ext in ('.lrc', '.jpg', '.png'):
                        sc = f"{base_p}{ext}"
                        if os.path.exists(sc):
                            try:
                                os.remove(sc)
                            except Exception:
                                pass

                # Clean up empty artist/album folder in Cravings
                try:
                    if old_dir and os.path.exists(old_dir) and not os.listdir(old_dir):
                        os.rmdir(old_dir)
                        parent_old = os.path.dirname(old_dir)
                        if parent_old and os.path.exists(parent_old) and not os.listdir(parent_old) and parent_old != self.paths.cravings_dir:
                            os.rmdir(parent_old)
                except Exception:
                    pass

                cursor.execute("UPDATE tracks SET status = 'PURGED' WHERE id = ?", (t_id,))
                purged_count += 1
                logger.info(f"Purged expired craving track {t_id} ({f_path}) after {retention_days} days retention")
            except Exception as e:
                logger.error(f"Failed purging craving track {t_id}: {e}")

        return purged_count

    def _check_release_radar(self):
        """Monitors new releases (singles) from most listened artists in Permanent."""
        radar_cfg = self.config.get('radar', {})
        if not radar_cfg.get('enabled', True):
            return

        interval = radar_cfg.get('check_interval_hours', 24) * 3600
        top_limit = radar_cfg.get('top_artists_limit', 10)

        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS system_metadata (key TEXT PRIMARY KEY, value TEXT)")
            cursor.execute("SELECT value FROM system_metadata WHERE key = 'last_radar_check'")
            row = cursor.fetchone()
            if row:
                try:
                    last_run = float(row[0])
                    if time.time() - last_run < interval:
                        return
                except ValueError:
                    pass

            logger.info("📡 Starting Daily Release Radar...")
            cursor.execute("REPLACE INTO system_metadata (key, value) VALUES ('last_radar_check', ?)", (str(time.time()),))

            cursor.execute('''
                SELECT artist FROM tracks 
                WHERE status = 'PERMANENT' AND artist != ''
                GROUP BY artist 
                ORDER BY COUNT(*) DESC LIMIT ?
            ''', (top_limit,))
            top_artists = [r[0] for r in cursor.fetchall()]
            conn.commit()

        if not top_artists:
            return

        from ytmusicapi import YTMusic
        yt = YTMusic()
        recommendations = []
        for artist in top_artists:
            try:
                search = yt.search(artist, filter="artists")
                if not search:
                    continue
                a_id = search[0]['browseId']
                a_data = yt.get_artist(a_id)

                if 'singles' in a_data and 'results' in a_data['singles']:
                    latest_single = a_data['singles']['results'][0]
                    s_title = latest_single.get('title')
                    s_id = latest_single.get('browseId')

                    if s_title and s_id:
                        with get_db_connection(self.db_path) as conn_chk:
                            c = conn_chk.cursor()
                            c.execute("SELECT id FROM tracks WHERE artist = ? AND title = ?", (artist, s_title))
                            if not c.fetchone():
                                logger.info(f"🚨 New release detected from {artist}! {s_title}")
                                from src.genre_resolver import resolve_genre
                                r_genre = resolve_genre(artist, s_title, db_path=self.db_path)
                                rec = TrackRecommendation(artist=artist, title=s_title, genre_context=r_genre, discovery_type="adjacent", reason="Release Radar Discovery")
                                recommendations.append(rec)
            except Exception as e:
                logger.error(f"Radar failure for {artist}: {e}")

        if recommendations:
            self.paths.ensure_dirs()
            self.curator.validate_and_save(recommendations, target_folder="Cinta", target_status="PENDING")

    def _check_daily_lyrics_scan(self):
        """Periodically runs lyrics scanning and upgrading."""
        lyrics_cfg = self.config.get('lyrics', {})
        if not lyrics_cfg.get('daily_scan_enabled', True):
            return

        interval = lyrics_cfg.get('scan_interval_hours', 24) * 3600

        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS system_metadata (key TEXT PRIMARY KEY, value TEXT)")
            cursor.execute("SELECT value FROM system_metadata WHERE key = 'last_lyrics_scan'")
            row = cursor.fetchone()
            if row:
                try:
                    last_run = float(row[0])
                    if time.time() - last_run < interval:
                        return
                except ValueError:
                    pass

            logger.info("🎤 Checking lyrics update and upgrade (periodic cycle)...")
            cursor.execute("REPLACE INTO system_metadata (key, value) VALUES ('last_lyrics_scan', ?)", (str(time.time()),))
            conn.commit()

        from src.enrich_lyrics import run_daily_lyrics_enrichment
        batch_limit = lyrics_cfg.get('daily_batch_limit', 50)
        upgrade_unsynced = lyrics_cfg.get('upgrade_unsynced', True)
        run_daily_lyrics_enrichment(self.db_path, limit=batch_limit, upgrade_unsynced=upgrade_unsynced)

    def _check_daily_genre_scan(self):
        """Runs periodic classification and assignment of genres to tracks lacking genres."""
        genres_cfg = self.config.get('genres', {})
        if not genres_cfg.get('daily_scan_enabled', True):
            return

        try:
            from src.genre_resolver import enrich_library_genres
            batch_limit = genres_cfg.get('daily_batch_limit', 35)
            enrich_library_genres(self.db_path, limit=batch_limit)
        except Exception as e:
            logger.warning(f"Error in periodic genre scan: {e}")

    def _run_internal(self, fill_mode: bool):
        """Core engine lifecycle loop."""
        start_time = time.time()
        promoted_count = 0
        purged_count = 0

        # Background periodic tasks
        self._check_release_radar()
        self._check_daily_lyrics_scan()
        self._check_daily_genre_scan()

        # 0. Intelligent state snapshot on every run (if enabled in config)
        if getattr(self.backup_manager, 'auto_backup_enabled', True):
            try:
                self.backup_manager.create_snapshot(tag="auto")
            except Exception as e:
                logger.warning(f"Error creating automatic state backup: {e}")

        logger.info(f"Starting engine cycle (fill_mode={fill_mode})")

        # 1. Proactive detection of physical folder changes in Permanent or Conveyor
        if self.config.get('playlists', {}).get('auto_update_on_change', True):
            self.playlists.check_and_update_if_modified()

        # 2. Reverse physical synchronization (Syncthing conflicts, manual moves, and ghost deletions)
        self.file_sync.clean_syncthing_conflicts()
        self.file_sync.sync_manual_moves()
        self.file_sync.clean_ghost_tracks()


        # 3. Telemetry and scrobbles
        processed_listens, _ = self.telemetry.process_listens()
        logger.info(f"New scrobbles processed: {processed_listens}")

        # 4. Shielding via Heart (ListenBrainz Loved Tracks)
        loved_tracks = self.telemetry.get_loved_tracks()
        if loved_tracks:
            loved_moved_count = 0
            with get_db_connection(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, artist, title, file_path, album FROM tracks WHERE status = 'CINTA' AND file_path IS NOT NULL")
                candidates = cursor.fetchall()

                if candidates:
                    from thefuzz import fuzz
                    artist_thresh = self.telemetry_config.get('loved_fuzzy_artist_threshold', 80)
                    title_thresh = self.telemetry_config.get('loved_fuzzy_title_threshold', 85)

                    for l_artist, l_title in loved_tracks:
                        l_art_l = l_artist.lower()
                        l_tit_l = l_title.lower()

                        for c_id, c_artist, c_title, c_path, c_album in candidates:
                            if not c_path or not os.path.exists(c_path):
                                continue

                            c_art_l = c_artist.lower()
                            c_tit_l = c_title.lower()

                            # Exact or fuzzy match
                            match = (l_art_l == c_art_l and l_tit_l == c_tit_l)
                            if not match:
                                s1 = fuzz.token_set_ratio(l_art_l, c_art_l)
                                s2 = fuzz.token_set_ratio(l_tit_l, c_tit_l)
                                match = (s1 >= artist_thresh and s2 >= title_thresh)

                            if match:
                                new_path = self.paths.get_permanente_track_path(c_artist, c_album, c_title)
                                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                                try:
                                    shutil.move(c_path, new_path)
                                    old_lrc = os.path.splitext(c_path)[0] + ".lrc"
                                    new_lrc = os.path.splitext(new_path)[0] + ".lrc"
                                    if os.path.exists(old_lrc):
                                        shutil.move(old_lrc, new_lrc)

                                    cursor.execute("UPDATE tracks SET status = 'PERMANENT', is_permanent = 1, file_path = ? WHERE id = ?", (new_path, c_id))
                                    loved_moved_count += 1
                                    logger.info(f"Heart on ListenBrainz! Shielded in Permanent: {c_artist} - {c_title} -> {new_path}")
                                except Exception as e:
                                    logger.error(f"Failed shielding by heart {c_id}: {e}")
                                break

                    conn.commit()

            if loved_moved_count > 0:
                self.playlists.update_all_playlists()

        # 5. Orphan scrobbles (songs played outside known catalog)
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orphan_scrobbles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artist TEXT,
                    title TEXT,
                    attempts INTEGER DEFAULT 0,
                    UNIQUE(artist, title)
                )
            """)
            cursor.execute("SELECT id, artist, title, attempts FROM orphan_scrobbles ORDER BY RANDOM()")
            orphans_db = cursor.fetchall()

            if orphans_db:
                logger.info(f"Processing {len(orphans_db)} pending orphan scrobbles...")
                for row in orphans_db:
                    o_id, artist, title, attempts = row
                    rec = TrackRecommendation(
                        title=title,
                        artist=artist,
                        genre_context="Variado",
                        discovery_type="adjacent",
                        reason="Detected on ListenBrainz"
                    )

                    val_count = self.curator.validate_and_save([rec])
                    if val_count > 0:
                        cursor.execute("DELETE FROM orphan_scrobbles WHERE id = ?", (o_id,))
                        logger.info(f"Orphan scrobble processed successfully: {artist} - {title}")
                    else:
                        cursor.execute("UPDATE orphan_scrobbles SET attempts = attempts + 1 WHERE id = ?", (o_id,))

                cursor.execute("DELETE FROM orphan_scrobbles WHERE attempts >= 2")
                conn.commit()

        # 6. Process requests mailbox and remote commands
        self.order_processor.process_peticiones()

        # 7. Lifecycle: Promotion and Purging on Conveyor
        is_fresh = self.telemetry.is_telemetry_fresh()

        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # --- PROMOTION VIA PLAY COUNT TO PERMANENT ---
            promo_count = self.conveyor_config.get('promotion_play_count', 15)
            cursor.execute("SELECT id, file_path, artist, album, title FROM tracks WHERE status = 'CINTA' AND play_count >= ?", (promo_count,))
            to_promote = cursor.fetchall()
            promoted_count = len(to_promote)

            for t_id, f_path, p_artist, p_album, p_title in to_promote:
                primary_artist = get_primary_artist(p_artist)
                new_path = self.paths.get_permanente_track_path(primary_artist, p_album, p_title)
                os.makedirs(os.path.dirname(new_path), exist_ok=True)

                try:
                    if f_path and os.path.exists(f_path):
                        shutil.move(f_path, new_path)
                        old_lrc = os.path.splitext(f_path)[0] + ".lrc"
                        new_lrc = os.path.splitext(new_path)[0] + ".lrc"
                        if os.path.exists(old_lrc):
                            shutil.move(old_lrc, new_lrc)

                    cursor.execute("""
                        UPDATE tracks 
                        SET status = 'PERMANENT', is_permanent = 1, file_path = ?
                        WHERE id = ?
                    """, (new_path, t_id))
                    logger.info(f"Promoted {t_id} to {new_path}")
                except Exception as e:
                    logger.error(f"Failed promoting {t_id}: {e}")

            # --- CONVEYOR PURGE ---
            if not is_fresh:
                logger.warning("Outdated telemetry. Skipping purge phase for safety.")
            else:
                grace_days = self.conveyor_config.get('grace_period_days', 150)
                cursor.execute(f"""
                    SELECT id, file_path FROM tracks 
                    WHERE status = 'CINTA' 
                    AND (julianday('now') - julianday(COALESCE(last_played_at, added_at))) > ?
                """, (grace_days,))
                to_purge_time = cursor.fetchall()

                cursor.execute(f"""
                    SELECT id, file_path FROM tracks
                    WHERE status = 'CINTA'
                    AND (
                        skip_count >= ?
                        OR (skip_count >= 3 AND (CAST(skip_count AS REAL) / (play_count + skip_count)) >= ?)
                    )
                """, (self.max_skips_before_purge, self.max_skip_ratio))
                to_purge_skip = cursor.fetchall()

                to_purge = list(set(to_purge_time + to_purge_skip))
                purged_count = len(to_purge)

                for t_id, f_path in to_purge:
                    try:
                        if f_path and os.path.exists(f_path):
                            os.remove(f_path)

                        if f_path:
                            base_p = os.path.splitext(f_path)[0]
                            for ext in ('.lrc', '.jpg', '.png'):
                                sc = f"{base_p}{ext}"
                                if os.path.exists(sc):
                                    try:
                                        os.remove(sc)
                                    except Exception:
                                        pass

                        cursor.execute("UPDATE tracks SET status = 'PURGED' WHERE id = ?", (t_id,))
                        logger.info(f"Purged track {t_id} ({f_path}) from Conveyor to PURGED status")
                    except Exception as e:
                        logger.error(f"Failed purging {t_id}: {e}")

            # --- CRAVINGS PURGE ---
            purged_cravings = self._purge_cravings(cursor)

            conn.commit()

            if promoted_count > 0 or purged_cravings > 0:
                self.playlists.update_all_playlists()
            elif purged_count > 0:
                self.playlists.update_cinta_playlists()

            # Auto-recovery of failed downloads (e.g. temporary connection drop)
            cursor.execute("UPDATE tracks SET status = 'PENDING' WHERE status = 'FAILED'")
            conn.commit()

            # --- CURATION AND REFILL PHASE ---
            cursor.execute("SELECT COUNT(*) FROM tracks WHERE status = 'CINTA' OR (status = 'PENDING' AND is_permanent = 0)")
            active_count = cursor.fetchone()[0]

            target_buffer = self.conveyor_config.get('buffer_size', 750)
            slots = target_buffer - active_count

            # In periodic mode, refill in progressive batches to avoid saturating bandwidth
            batch_to_curate = slots if fill_mode else min(slots, self.curation_batch_per_cycle)

            if batch_to_curate > 0:
                logger.info(f"Conveyor refill: Searching for {batch_to_curate} new tracks (total slots: {slots})")
                validated = self.curator.run_curation_cycle(batch_to_curate)
                logger.info(f"LLM Curator provided {validated} new tracks")

            # --- DOWNLOAD PENDING PHASE ---
            total_downloaded = 0
            while True:
                cursor.execute("SELECT COUNT(*) FROM tracks WHERE status = 'PENDING'")
                remaining = cursor.fetchone()[0]
                if remaining == 0:
                    break

                logger.info(f"{remaining} PENDING tracks in queue. Starting download batch...")
                downloaded = self.downloader.download_pending_tracks(retry_failed=True)
                total_downloaded += downloaded

                cursor.execute("SELECT COUNT(*) FROM tracks WHERE status = 'PENDING'")
                new_remaining = cursor.fetchone()[0]
                logger.info(f"Batch completed. Downloaded: {downloaded} | Remaining in queue: {new_remaining}")

                if new_remaining > 0:
                    if not fill_mode and total_downloaded >= self.cycle_max_downloads:
                        logger.info(f"Per-cycle download limit reached ({self.cycle_max_downloads} songs). Remainder will continue next cycle.")
                        break
                    time.sleep(3)
                else:
                    break

            logger.info(f"Download phase finished. Total downloaded this cycle: {total_downloaded}")

        # 8. Process physical file local ratings and regenerate playlists
        self.file_sync.process_local_file_ratings()
        self.playlists.update_all_playlists()
        logger.info("Engine cycle completed successfully")

        # 9. Consolidated desktop notification
        elapsed_sec = int(time.time() - start_time)
        time_str = f"{elapsed_sec // 60}m {elapsed_sec % 60}s" if elapsed_sec >= 60 else f"{elapsed_sec}s"

        body_lines = [f"⏱ Total time: {time_str}"]
        if total_downloaded > 0:
            body_lines.append(f"📥 {total_downloaded} new songs downloaded")
        if processed_listens > 0:
            body_lines.append(f"🎧 {processed_listens} scrobbles synced")
        if promoted_count > 0:
            body_lines.append(f"⭐ {promoted_count} promoted to Permanent")
        if purged_count > 0:
            body_lines.append(f"🧹 {purged_count} tracks rotated/purged")
        body_lines.append("📁 M3U8 playlists and library updated")

        send_notification(f"🎵 Music Engine Synchronized ({time_str})", "\n".join(body_lines), enabled=self.notifications_enabled)
