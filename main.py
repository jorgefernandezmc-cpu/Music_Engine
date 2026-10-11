import argparse
import sys
import sqlite3
import os
from datetime import datetime
from src.engine import MusicEngine
from src.ytm_extractor import YTMExtractor
from src.telemetry import TelemetryEngine
from src.playlist_gen import PlaylistGenerator

def get_status(db_path="data/conveyor_state.sqlite", storage_dir="storage"):
    if not os.path.exists(db_path):
        print("La base de datos no está inicializada.")
        return
        
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        counts = {}
        for status in ['CINTA', 'PERMANENT', 'PENDING', 'PURGED']:
            cursor.execute("SELECT COUNT(*) FROM tracks WHERE status = ?", (status,))
            counts[status] = cursor.fetchone()[0]
            
        cursor.execute("SELECT value FROM system_metadata WHERE key = 'last_listenbrainz_sync'")
        row = cursor.fetchone()
        last_sync = datetime.fromtimestamp(int(row[0])).isoformat() if row and row[0] else "Nunca"
        
        cursor.execute("SELECT MAX(listened_at) FROM listen_events")
        row = cursor.fetchone()
        last_scrobble = row[0] if row else "Ninguno"
        
    def get_size(start_path = '.'):
        total_size = 0
        for dirpath, _, filenames in os.walk(start_path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp):
                    total_size += os.path.getsize(fp)
        return total_size
        
    size_bytes = get_size(storage_dir) if os.path.exists(storage_dir) else 0
    size_mb = size_bytes / (1024 * 1024)
    size_gb = size_bytes / (1024 * 1024 * 1024)
    size_str = f"{size_gb:.2f} GB" if size_gb > 1 else f"{size_mb:.2f} MB"
    
    print("\n" + "="*40)
    print(" ESTADO DE LA CINTA TRANSPORTADORA")
    print("="*40)
    print(f"Pistas en CINTA:     {counts['CINTA']}")
    print(f"Pistas PERMANENTES:  {counts['PERMANENT']}")
    print(f"Pistas PENDIENTES:   {counts['PENDING']}")
    print(f"Pistas PURGADAS:     {counts['PURGED']}")
    print("-" * 40)
    print(f"Espacio en storage:  {size_str}")
    print(f"Último scrobble:     {last_scrobble}")
    print(f"Última sync LB:      {last_sync}")
    print("="*40 + "\n")


def main():
    parser = argparse.ArgumentParser(description="La Cinta Transportadora - Motor Musical Autónomo")
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles")
    
    run_parser = subparsers.add_parser("run", help="Ejecuta el ciclo completo del motor")
    run_parser.add_argument("--fill", action="store_true", help="Fuerza la ejecución continua hasta llenar la Cinta")
    
    import_p = subparsers.add_parser("import-playlist", help="Importa una playlist como permanente")
    import_p.add_argument("url_or_id", help="URL o ID de la playlist de YouTube Music")
    
    subparsers.add_parser("sync-telemetry", help="Sincroniza scrobbles sin descargar nada")
    subparsers.add_parser("status", help="Muestra el estado de la base de datos y ocupación")
    subparsers.add_parser("update-playlists", help="Regenera todas las listas .m3u8")
    
    args = parser.parse_args()
    
    db_path = "data/conveyor_state.sqlite"
    config_path = "config/config.yaml"
    
    if args.command == "run":
        from dotenv import load_dotenv
        load_dotenv("config/.env")
        
        missing = []
        if not os.getenv("GEMINI_API_KEY") or "your_" in os.getenv("GEMINI_API_KEY", ""):
            missing.append("GEMINI_API_KEY")
        if not os.getenv("LISTENBRAINZ_USER") or "your_" in os.getenv("LISTENBRAINZ_USER", ""):
            missing.append("LISTENBRAINZ_USER")
        if not os.getenv("LISTENBRAINZ_TOKEN") or "your_" in os.getenv("LISTENBRAINZ_TOKEN", ""):
            missing.append("LISTENBRAINZ_TOKEN")
            
        if missing:
            print("ERROR: Faltan variables críticas en config/.env o contienen valores por defecto:")
            for m in missing:
                print(f" - {m}")
            print("\nPor favor, edita config/.env y configúralas antes de continuar.")
            sys.exit(1)
            
        engine = MusicEngine(db_path, config_path)
        engine.run(fill_mode=args.fill)
    elif args.command == "import-playlist":
        url_or_id = args.url_or_id
        playlist_id = url_or_id
        if "list=" in url_or_id:
            playlist_id = url_or_id.split("list=")[1].split("&")[0]
            
        print(f"Importando playlist: {playlist_id}")
        extractor = YTMExtractor(db_path, "storage/Permanente", "config/headers_auth.json")
        title, tracks = extractor.extract_playlist(playlist_id)
        extractor.generate_taste_profile()
        print(f"Playlist '{title}' indexada. ({len(tracks)} pistas pendientes de descarga).")
        print("Ejecuta 'python main.py run' para descargar físicamente las pistas.")
    elif args.command == "sync-telemetry":
        tel = TelemetryEngine(db_path, config_path)
        processed = tel.process_listens()
        print(f"Telemetría sincronizada. {processed} nuevos scrobbles procesados.")
    elif args.command == "status":
        get_status(db_path, "storage")
    elif args.command == "update-playlists":
        pg = PlaylistGenerator(db_path, "storage")
        pg.update_all_playlists()
        print("Listas actualizadas.")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
