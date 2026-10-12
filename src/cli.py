import argparse
import sys
import os
from datetime import datetime
from src.paths import StoragePaths
from src.db import get_db_connection
from src.engine import MusicEngine
from src.ytm_extractor import YTMExtractor
from src.telemetry import TelemetryEngine
from src.playlist_gen import PlaylistGenerator
from src.downloader import Downloader

def get_status(db_path="data/conveyor_state.sqlite", config_path="config/config.yaml"):
    paths = StoragePaths(config_path)
    storage_dir = paths.base_dir
    
    if not os.path.exists(db_path):
        print("Database is not initialized. Run 'python database/init_db.py' first.")
        return
        
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        
        counts = {}
        for status in ['CINTA', 'PERMANENT', 'ANTOJO', 'PENDING', 'PURGED']:
            cursor.execute("SELECT COUNT(*) FROM tracks WHERE status = ?", (status,))
            counts[status] = cursor.fetchone()[0]
            
        cursor.execute("SELECT value FROM system_metadata WHERE key = 'last_listenbrainz_sync'")
        row = cursor.fetchone()
        last_sync = datetime.fromtimestamp(int(row[0])).isoformat() if row and row[0] else "Never"
        
        cursor.execute("SELECT MAX(listened_at) FROM listen_events")
        row = cursor.fetchone()
        last_scrobble = row[0] if row else "None"
        
    def get_size(start_path):
        total_size = 0
        if not os.path.exists(start_path):
            return 0
        for dirpath, _, filenames in os.walk(start_path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp):
                    total_size += os.path.getsize(fp)
        return total_size
        
    size_bytes = get_size(storage_dir)
    size_mb = size_bytes / (1024 * 1024)
    size_gb = size_bytes / (1024 * 1024 * 1024)
    size_str = f"{size_gb:.2f} GB" if size_gb > 1 else f"{size_mb:.2f} MB"
    
    print("\n" + "="*45)
    print(" CONVEYOR BELT STATUS")
    print("="*45)
    print(f"Base directory:     {storage_dir}")
    print(f"Tracks in CONVEYOR: {counts['CINTA']}")
    print(f"PERMANENT tracks:   {counts['PERMANENT']}")
    print(f"CRAVINGS tracks:    {counts['ANTOJO']}")
    print(f"PENDING tracks:     {counts['PENDING']}")
    print(f"PURGED tracks:      {counts['PURGED']}")
    print("-" * 45)
    print(f"Disk space used:    {size_str}")
    print(f"Last scrobble:      {last_scrobble}")
    print(f"Last LB sync:       {last_sync}")
    print("="*45 + "\n")


def main():
    parser = argparse.ArgumentParser(description="The Conveyor Belt - Autonomous Music Engine")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    run_parser = subparsers.add_parser("run", help="Executes full engine cycle")
    run_parser.add_argument("--fill", action="store_true", help="Forces continuous run until Conveyor buffer is full")
    
    import_p = subparsers.add_parser("import-playlist", help="Imports a YouTube Music playlist as permanent")
    import_p.add_argument("url_or_id", help="URL or ID of YouTube Music playlist")
    import_p.add_argument("--download", action="store_true", help="Download tracks immediately after indexing")
    import_p.add_argument("--no-album-search", action="store_true", help="Do not search for studio album versions (use as listed)")

    dl_parser = subparsers.add_parser("download-pending", help="Downloads all tracks in PENDING queue without invoking AI curator")
    
    fix_parser = subparsers.add_parser("fix-metadata", help="Audits and auto-repairs questionable or mismatched tracks (covers, 8-bit, karaoke, etc.)")
    fix_parser.add_argument("--use-ai", action="store_true", help="Uses AI (Gemini) as last resort if heuristics find no reliable match")

    subparsers.add_parser("sync-telemetry", help="Synchronizes scrobbles without downloading audio")
    subparsers.add_parser("status", help="Displays database status and disk usage")
    subparsers.add_parser("update-playlists", help="Regenerates all .m3u8 playlists (and Lune backup if enabled in config)")
    watch_p = subparsers.add_parser("watch-folders", help="Monitors folder changes in Permanent and Conveyor, updating playlists in real time")
    watch_p.add_argument("--interval", type=int, default=5, help="Interval in seconds between checks (default: 5)")
    
    set_alb_p = subparsers.add_parser("set-album", help="Reassigns a permanent track to a specific album and moves physical files")
    set_alb_p.add_argument("song_query", help="Track name or artist")
    set_alb_p.add_argument("new_album", help="Target official album name")

    enrich_p = subparsers.add_parser("enrich-lyrics", help="Scans and upgrades lyrics for existing tracks")
    enrich_p.add_argument("--limit", type=int, default=50, help="Maximum tracks to process (default: 50, 0=all)")
    enrich_p.add_argument("--all", action="store_true", help="Process entire library without limit")
    enrich_p.add_argument("--no-upgrade", action="store_true", help="Do not attempt to upgrade plain lyrics to synced")

    enrich_g = subparsers.add_parser("enrich-genres", help="Classifies and assigns exact music genres in metadata and SQLite")
    enrich_g.add_argument("--limit", type=int, default=50, help="Maximum tracks to process (default: 50, 0=all)")
    enrich_g.add_argument("--all", action="store_true", help="Process all tracks pending genre without limit")
    enrich_g.add_argument("--force-all", action="store_true", help="Reclassify even tracks with already assigned genres")
    enrich_g.add_argument("--no-ai", action="store_true", help="Disable Gemini completely and rely exclusively on open sources (MusicBrainz/Deezer)")

    enrich_m = subparsers.add_parser("enrich-metadata", help="Enriches track number and release date across library and tags")
    enrich_m.add_argument("--limit", type=int, default=0, help="Maximum tracks to process (0=all)")
    enrich_m.add_argument("--force-all", action="store_true", help="Reprocess even tracks with existing track numbers and dates")

    # Intelligent backup & restoration subcommands
    backup_p = subparsers.add_parser("backup", help="Creates or manages intelligent state backups and snapshots")
    backup_p.add_argument("--tag", default="manual", help="Optional label or tag for the snapshot (default: manual)")
    backup_p.add_argument("--force", action="store_true", help="Force snapshot even if state has not changed (bypasses hash deduplication)")
    backup_p.add_argument("--list", action="store_true", help="List all existing snapshots and their sizes/dates")

    export_p = subparsers.add_parser("export-backup", help="Exports a complete portable migration bundle (.tar.gz) for moving to another PC")
    export_p.add_argument("--output", "-o", default=None, help="Target destination path for the exported .tar.gz bundle")

    restore_p = subparsers.add_parser("restore-backup", help="Restores a snapshot (.sqlite/.sqlite.gz) or migration bundle (.tar.gz)")
    restore_p.add_argument("source", help="Path to the backup file (.sqlite, .sqlite.gz or .tar.gz)")
    restore_p.add_argument("--target-base-dir", default=None, help="New base music directory if paths need to be rebased for this computer")
    restore_p.add_argument("--no-rebase", action="store_true", help="Do not rebase file paths inside tracks database")

    args = parser.parse_args()

    db_path = "data/conveyor_state.sqlite"
    config_path = "config/config.yaml"
    
    if args.command == "run":
        from dotenv import load_dotenv
        load_dotenv("config/.env")
        
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key or "your_" in gemini_key:
            print("ERROR: GEMINI_API_KEY is missing or contains default placeholder in config/.env.")
            print("Please edit config/.env and configure your Gemini API key before continuing.")
            sys.exit(1)
            
        lb_user = os.getenv("LISTENBRAINZ_USER")
        lb_token = os.getenv("LISTENBRAINZ_TOKEN")
        if not lb_user or "your_" in lb_user or not lb_token or "your_" in lb_token:
            print("[Info] ListenBrainz credentials not configured in config/.env. Continuing without telemetry scrobble sync.")
            
        engine = MusicEngine(db_path, config_path)
        engine.run(fill_mode=args.fill)
    elif args.command == "import-playlist":
        url_or_id = args.url_or_id
        playlist_id = url_or_id
        if "list=" in url_or_id:
            playlist_id = url_or_id.split("list=")[1].split("&")[0]
            
        print(f"Importing playlist: {playlist_id}")
        extractor = YTMExtractor(db_path, config_path, "config/headers_auth.json")
        resolve_albums = not args.no_album_search
        title, tracks = extractor.extract_playlist(playlist_id, resolve_albums=resolve_albums)
        extractor.generate_taste_profile()
        print(f"\nPlaylist '{title}' indexed successfully. ({len(tracks)} tracks assigned to Permanent).")
        
        if args.download:
            print("\nStarting physical download of imported tracks...")
            dl = Downloader(db_path, config_path)
            total_dl = 0
            while True:
                downloaded = dl.download_pending_tracks()
                if downloaded == 0:
                    break
                total_dl += downloaded
                print(f"Downloaded {total_dl}/{len(tracks)} tracks...")
            print("Downloads completed!")
            pg = PlaylistGenerator(db_path, config_path)
            pg.update_all_playlists()
            print("M3U8 playlists updated.")
        else:
            print("Run 'python main.py download-pending' or 'python main.py run' to download them physically.")
    elif args.command == "download-pending":
        print("Starting download of pending tracks...")
        with get_db_connection(db_path) as conn:
            conn.execute("UPDATE tracks SET status = 'PENDING' WHERE status = 'FAILED'")
            conn.commit()
            
        dl = Downloader(db_path, config_path)
        total_dl = 0
        while True:
            downloaded = dl.download_pending_tracks(retry_failed=False)
            if downloaded == 0:
                break
            total_dl += downloaded
            print(f"Batch completed (+{downloaded} tracks). Total downloaded: {total_dl}")
        print("Download queue finished.")
        pg = PlaylistGenerator(db_path, config_path)
        pg.update_all_playlists()
        print("M3U8 playlists updated.")
    elif args.command == "fix-metadata":
        from ytmusicapi import YTMusic
        from src.album_resolver import auto_fix_track, FORBIDDEN_WORDS, is_suspicious_match
        
        print("Starting audit and auto-repair of questionable tracks...")
        yt = YTMusic()
        client = None
        if args.use_ai:
            from dotenv import load_dotenv
            load_dotenv("config/.env")
            from google import genai
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key and "your_" not in api_key:
                client = genai.Client(api_key=api_key)
                print("[*] Gemini activated as last resort for questionable matches.")
                
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, artist, album, file_path FROM tracks")
            all_tracks = cursor.fetchall()
            
            fixed_count = 0
            checked_count = 0
            
            known_suspect_vids = set()
            auditoria_file = "../Herramientas/Sincronizador_YT/registros/auditoria_sospechosas.txt"
            if os.path.exists(auditoria_file):
                import re
                with open(auditoria_file, 'r', encoding='utf-8') as af:
                    known_suspect_vids = set(re.findall(r'watch\?v=([a-zA-Z0-9_-]+)', af.read()))
            
            for t_id, t_title, t_artist, t_album, f_path in all_tracks:
                needs_check = (
                    t_id in known_suspect_vids or
                    any(fw in t_title.lower() or fw in (t_album or '').lower() or fw in t_artist.lower() for fw in FORBIDDEN_WORDS)
                )
                
                if not needs_check:
                    continue
                    
                checked_count += 1
                print(f"[*] Analyzing questionable case: {t_artist} - {t_title} (Current ID: {t_id})...")
                fixed = auto_fix_track(yt, t_artist, t_title, current_vid=t_id, client=client)
                
                if fixed.get('fixed') and fixed.get('id') != t_id:
                    new_vid = fixed['id']
                    cursor.execute("SELECT id FROM tracks WHERE id = ?", (new_vid,))
                    existing = cursor.fetchone()
                    if existing:
                        cursor.execute("DELETE FROM tracks WHERE id = ?", (t_id,))
                    else:
                        cursor.execute("""
                            UPDATE tracks 
                            SET id = ?, album = ? 
                            WHERE id = ?
                        """, (new_vid, fixed.get('album', t_album), t_id))
                    fixed_count += 1
                    print(f"  [✓] Fixed via {fixed.get('method')}: New ID -> {new_vid}")
                else:
                    print(f"  [-] Retained current ID (or no change required): {t_id}")
                    
            conn.commit()
            print(f"\nAudit completed. {checked_count} analyzed, {fixed_count} tracks fixed successfully.")
    elif args.command == "sync-telemetry":
        tel = TelemetryEngine(db_path, config_path)
        processed, _ = tel.process_listens()
        print(f"Telemetry synchronized. {processed} new scrobbles processed.")
    elif args.command == "status":
        get_status(db_path, config_path)
    elif args.command == "update-playlists":
        pg = PlaylistGenerator(db_path, config_path)
        pg.update_all_playlists()
        print("Playlists updated successfully.")
    elif args.command == "watch-folders":
        import time
        pg = PlaylistGenerator(db_path, config_path)
        print(f"Monitoring Permanent and Conveyor folders (every {args.interval}s)... Press Ctrl+C to stop.")
        pg.check_and_update_if_modified()
        try:
            while True:
                time.sleep(args.interval)
                pg.check_and_update_if_modified()
        except KeyboardInterrupt:
            print("\nMonitoring stopped.")
    elif args.command == "set-album":
        from src.order_processor import OrderProcessor
        pg = PlaylistGenerator(db_path, config_path)
        processor = OrderProcessor(db_path, config_path, playlists=pg)
        with get_db_connection(db_path) as conn:
            ok, msg = processor.process_album_move(conn, args.song_query, args.new_album)
            if ok:
                print(f"[✓] Success: {msg}")
            else:
                print(f"[-] {msg}")
    elif args.command == "enrich-lyrics":
        from src.enrich_lyrics import run_daily_lyrics_enrichment
        limit = 0 if args.all else args.limit
        print(f"Starting lyrics scan and update (Limit: {'No limit' if limit == 0 else limit} tracks)...")
        stats = run_daily_lyrics_enrichment(db_path, limit=limit, upgrade_unsynced=not args.no_upgrade)
        print("\nResults:")
        print(f" - Processed:           {stats['processed']}")
        print(f" - New lyrics assigned: {stats['new_lyrics']}")
        print(f" - Upgraded to synced:  {stats['upgraded_to_synced']}")
        print(f" - Unchanged:           {stats['unchanged']}")
    elif args.command == "enrich-genres":
        from src.genre_resolver import enrich_library_genres
        limit = 0 if args.all else args.limit
        print(f"Starting genre enrichment (Limit: {'No limit' if limit == 0 else limit} tracks, AI: {'Disabled' if args.no_ai else 'Last resort only'})...")
        stats = enrich_library_genres(db_path, limit=limit, force_all=args.force_all, allow_ai=not args.no_ai)
        print("\nResults:")
        print(f" - Processed: {stats['processed']}")
        print(f" - Updated:   {stats['updated']}")
    elif args.command == "enrich-metadata":
        from src.enrich_track_meta import enrich_library_metadata
        limit = args.limit
        print(f"Starting track and release date enrichment (Limit: {'No limit' if limit == 0 else limit} tracks)...")
        stats = enrich_library_metadata(db_path, force_all=args.force_all, limit=limit)
        print("\nResults:")
        print(f" - Songs evaluated:    {stats['total_songs']}")
        print(f" - Albums processed:   {stats['albums_processed']}")
        print(f" - Tracks assigned:    {stats['tracks_assigned']}")
        print(f" - Dates assigned:     {stats['dates_assigned']}")
        print(f" - Tagged files:       {stats['files_tagged']}")
    elif args.command == "backup":
        from src.backup_manager import BackupManager
        bm = BackupManager(db_path, config_path)
        if args.list:
            backups = bm.list_backups()
            print(f"\n=======================================================")
            print(f" AVAILABLE SNAPSHOTS ({len(backups)} in {bm.backup_dir})")
            print(f"=======================================================")
            if not backups:
                print(" No snapshots found.")
            else:
                for b in backups:
                    size_kb = b["size_bytes"] / 1024
                    tag_display = f" [{b['tag']}]" if b.get('tag') else ""
                    format_display = f" | Format: {b.get('format', 'unknown')}"
                    print(f" • {b['filename']}{tag_display}")
                    print(f"    Date: {b['date']} | Size: {size_kb:.1f} KB{format_display}")
            print("=======================================================\n")
        else:
            created = bm.create_snapshot(tag=args.tag, force=args.force)
            if created:
                print(f"[✓] Backup snapshot successfully saved: {created}")
            else:
                print("[i] State unchanged since last snapshot. Deduplication skipped redundant backup (use --force to override).")
    elif args.command == "export-backup":
        from src.backup_manager import BackupManager
        bm = BackupManager(db_path, config_path)
        exported = bm.export_full_bundle(output_path=args.output)
        print(f"[✓] Migration bundle exported successfully: {exported}")
        print("    You can copy this file to another machine and run:")
        print(f"    python main.py restore-backup {os.path.basename(exported)}")
    elif args.command == "restore-backup":
        from src.backup_manager import BackupManager
        bm = BackupManager(db_path, config_path)
        print(f"Restoring backup from: {args.source}...")
        res = bm.restore_backup(
            backup_source=args.source,
            target_base_dir=args.target_base_dir,
            rebase_paths=not args.no_rebase
        )
        print("\n=======================================================")
        print(" RESTORE SUMMARY")
        print("=======================================================")
        print(f" - Total tracks in database: {res['total_tracks']}")
        print(f" - Rebased path references:  {res['rebased_count']}")
        print(f" - Components restored:      {', '.join(res['restored_components'])}")
        if res.get('old_base') and res.get('new_base') and res['old_base'] != res['new_base']:
            print(f" - Base directory rebased:   '{res['old_base']}' -> '{res['new_base']}'")
        print("=======================================================\n")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
