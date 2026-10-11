import os
import sqlite3
import logging
import yaml
import shutil
from filelock import FileLock, Timeout
from src.telemetry import TelemetryEngine
from src.curator_llm import CuratorLLM
from src.downloader import Downloader
from src.curator_llm import TrackRecommendation
from src.playlist_gen import PlaylistGenerator

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
        
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
            
        self.conveyor_config = self.config.get('conveyor', {})
        self.telemetry = TelemetryEngine(db_path, config_path)
        self.curator = CuratorLLM(db_path, config_path)
        self.downloader = Downloader(db_path, config_path)
        self.playlists = PlaylistGenerator(db_path)
        
    def run(self, fill_mode=False):
        os.makedirs('data', exist_ok=True)
        lock_path = "data/engine.lock"
        try:
            with FileLock(lock_path, timeout=1):
                self._run_internal(fill_mode)
        except Timeout:
            logger.warning("Motor en ejecución. Saliendo.")
            
    def _sync_manual_moves(self):
        """
        Escanea storage/Permanente para encontrar archivos que hayan sido
        movidos manualmente desde Cinta. Si encuentra coincidencias,
        actualiza la base de datos para marcarlas como PERMANENT.
        """
        permanente_dir = os.path.join("storage", "Permanente")
        if not os.path.exists(permanente_dir):
            return
            
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, file_path FROM tracks WHERE status != 'PERMANENT'")
            non_perm_tracks = cursor.fetchall()
            
            basename_map = {}
            for t_id, f_path in non_perm_tracks:
                if f_path:
                    basename = os.path.basename(f_path)
                    basename_map[basename] = t_id
                    
            updated_count = 0
            for root, dirs, files in os.walk(permanente_dir):
                for file in files:
                    if file.endswith(('.opus', '.m4a', '.mp3')):
                        if file in basename_map:
                            t_id = basename_map[file]
                            # Construir la ruta relativa desde la carpeta raíz del proyecto
                            new_rel_path = os.path.relpath(os.path.join(root, file), ".")
                            
                            cursor.execute("""
                                UPDATE tracks 
                                SET status = 'PERMANENT', is_permanent = 1, file_path = ?
                                WHERE id = ?
                            """, (new_rel_path, t_id))
                            updated_count += 1
                            logger.info(f"Movimiento manual detectado y sincronizado: {file} -> PERMANENT")
                            
            if updated_count > 0:
                conn.commit()
                logger.info(f"Sincronizador Inverso: {updated_count} pistas actualizadas a PERMANENT.")

    def _clean_ghost_tracks(self):
        """
        Escanea la BD en busca de pistas cuyos archivos físicos hayan
        sido eliminados por el usuario. Si no existen, las marca como PURGED.
        Incluye un seguro anti-desastres (Mass Deletion Failsafe).
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, file_path FROM tracks WHERE status IN ('CINTA', 'ANTOJO', 'PERMANENT')")
            cinta_tracks = cursor.fetchall()
            
            missing_tracks = []
            for t_id, f_path in cinta_tracks:
                if f_path and not os.path.exists(f_path):
                    missing_tracks.append((t_id, f_path))
                    
            if len(missing_tracks) > 50:
                logger.error(f"¡CRÍTICO! Se han detectado {len(missing_tracks)} archivos borrados de golpe.")
                logger.error("Abortando limpieza de fantasmas para evitar purga masiva accidental (posible fallo de Syncthing o SD extraída).")
                return
                
            ghost_count = 0
            for t_id, f_path in missing_tracks:
                new_status = 'ARCHIVED' if 'Antojos' in f_path else 'PURGED'
                cursor.execute("UPDATE tracks SET status = ? WHERE id = ?", (new_status, t_id))
                ghost_count += 1
                logger.info(f"Limpiador de Fantasmas: Archivo borrado detectado. Estado {new_status} para {t_id}")
                
            if ghost_count > 0:
                conn.commit()
                logger.info(f"Limpiador de Fantasmas: {ghost_count} pistas marcadas como PURGED.")


    def _check_auto_antojos(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    SELECT artist, genre FROM tracks 
                    WHERE status = 'PERMANENT' AND added_at > datetime('now', '-7 days')
                    GROUP BY artist 
                    HAVING COUNT(*) >= 3
                ''')
                obsessions = cursor.fetchall()
                
                for artist, genre in obsessions:
                    if not artist: continue
                    
                    # Prevent trigger if the user already has a lot of tracks for this artist
                    cursor.execute("SELECT COUNT(*) FROM tracks WHERE artist = ?", (artist,))
                    total_tracks = cursor.fetchone()[0]
                    
                    if total_tracks > 15:
                        continue # Already heavily documented artist
                        
                    folder_name = f"{artist.replace(' ', '_')}_Sorpresa"

                    target_folder = os.path.join("storage", "Antojos", folder_name)
                    
                    if not os.path.exists(target_folder):
                        logger.info(f"Auto-Antojo detectado: ¡Te has obsesionado con {artist}! Generando sorpresa...")
                        os.makedirs(target_folder, exist_ok=True)
                        groups = self.curator.run_auto_antojo(artist, genre or "Variado")
                        val_intent = 0
                        for group in groups:
                            val_intent += self.curator.validate_and_save(group.tracks, target_folder=f"Antojos/{group.folder_name}", target_status="PENDING_ANTOJO")
                        logger.info(f"Auto-Antojo insertó {val_intent} pistas sorpresa para {artist}.")
        except Exception as e:
            logger.error(f"Error comprobando Auto-Antojos: {e}")




    def _process_local_file_ratings(self):
        import mutagen
        import shutil
        
        for dirpath, _, filenames in os.walk("storage"):
            for f in filenames:
                if not f.endswith(('.opus', '.mp3', '.flac', '.m4a')):
                    continue
                    
                filepath = os.path.join(dirpath, f)
                
                try:
                    audio = mutagen.File(filepath)
                    if not audio: continue
                    
                    rating = 0
                    
                    # Opus / FLAC (Vorbis comments)
                    if 'RATING' in audio:
                        try:
                            val = int(audio['RATING'][0])
                            rating = val if val <= 5 else int(val / 20)
                        except: pass
                    
                    # MP3 (ID3 POPM)
                    elif hasattr(audio, 'tags') and audio.tags:
                        for tag in audio.tags.values():
                            if tag.FrameID == 'POPM':
                                val = tag.rating
                                if val >= 196: rating = 5
                                elif val >= 128: rating = 4
                                elif val >= 64: rating = 3
                                elif val >= 1: rating = 1
                                break

                    if rating == 0:
                        continue

                    # Get DB track
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT id, status, is_permanent FROM tracks WHERE file_path = ?", (filepath,))
                        row = cursor.fetchone()
                        
                        if not row: continue
                        t_id, status, is_permanent = row
                        
                        if rating == 1:
                            # Purge
                            audio.delete() # Remove tags to prevent resync loops just in case
                            try: os.remove(filepath)
                            except: pass
                            new_status = 'ARCHIVED' if 'Antojos' in filepath else 'PURGED'
                            cursor.execute("UPDATE tracks SET status = ?, file_path = NULL WHERE id = ?", (new_status, t_id))
                            logger.info(f"Musicolet Rating 1: Purgado {filepath}.")
                            
                        elif rating == 4 and "Descubrimientos_Favoritos" not in filepath:
                            target_dir = "storage/Permanente/Descubrimientos_Favoritos"
                            os.makedirs(target_dir, exist_ok=True)
                            new_path = os.path.join(target_dir, os.path.basename(filepath))
                            # Remove rating tag so we don't process it endlessly
                            if 'RATING' in audio: del audio['RATING']
                            audio.save()
                            shutil.move(filepath, new_path)
                            cursor.execute("UPDATE tracks SET status = 'PERMANENT', is_permanent = 1, file_path = ? WHERE id = ?", (new_path, t_id))
                            logger.info(f"Musicolet Rating 4: Movido a Descubrimientos Favoritos -> {new_path}.")
                            
                        elif rating == 5 and "Favorite Songs" not in filepath:
                            target_dir = "storage/Permanente/Favorite Songs"
                            os.makedirs(target_dir, exist_ok=True)
                            new_path = os.path.join(target_dir, os.path.basename(filepath))
                            # Remove rating tag so we don't process it endlessly
                            if 'RATING' in audio: del audio['RATING']
                            audio.save()
                            shutil.move(filepath, new_path)
                            cursor.execute("UPDATE tracks SET status = 'PERMANENT', is_permanent = 1, file_path = ? WHERE id = ?", (new_path, t_id))
                            logger.info(f"Musicolet Rating 5: Movido a Favorite Songs -> {new_path}.")
                            
                except Exception as e:
                    continue



    def _check_release_radar(self):
        # Run daily check
        import time
        from ytmusicapi import YTMusic
        
        top_artists = []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Check last run
            cursor.execute("CREATE TABLE IF NOT EXISTS system_metadata (key TEXT PRIMARY KEY, value TEXT)")
            cursor.execute("SELECT value FROM system_metadata WHERE key = 'last_radar_check'")
            row = cursor.fetchone()
            if row:
                last_run = float(row[0])
                if time.time() - last_run < 86400: # 24 hours
                    return
            
            logger.info("📡 Iniciando Radar de Novedades Diario...")
            cursor.execute("REPLACE INTO system_metadata (key, value) VALUES ('last_radar_check', ?)", (str(time.time()),))
            
            # Get top 10 permanent artists
            cursor.execute('''
                SELECT artist FROM tracks 
                WHERE status = 'PERMANENT' AND artist != ''
                GROUP BY artist 
                ORDER BY COUNT(*) DESC LIMIT 10
            ''')
            top_artists = [r[0] for r in cursor.fetchall()]
            
        # Outside the connection
        yt = YTMusic()
        recommendations = []
        for artist in top_artists:
            try:
                search = yt.search(artist, filter="artists")
                if not search: continue
                a_id = search[0]['browseId']
                a_data = yt.get_artist(a_id)
                
                if 'singles' in a_data and 'results' in a_data['singles']:
                    latest_single = a_data['singles']['results'][0]
                    s_title = latest_single.get('title')
                    s_id = latest_single.get('browseId')
                    
                    if s_title and s_id:
                        # Check if we already have it with a fresh connection
                        with sqlite3.connect(self.db_path) as conn_chk:
                            c = conn_chk.cursor()
                            c.execute("SELECT id FROM tracks WHERE artist = ? AND title = ?", (artist, s_title))
                            if not c.fetchone():
                                logger.info(f"🚨 ¡Novedad detectada de {artist}! {s_title}")
                                from src.curator_llm import TrackRecommendation
                                rec = TrackRecommendation(artist=artist, title=s_title, genre_context="Variado", discovery_type="adjacent", reason="Novedad del Radar")
                                recommendations.append(rec)
            except Exception as e:
                logger.error(f"Fallo en radar para {artist}: {e}")
                
        if recommendations:
            target_folder = "storage/Cinta"
            os.makedirs(target_folder, exist_ok=True)
            self.curator.validate_and_save(recommendations, target_folder="Cinta", target_status="PENDING")

                    
    def _run_internal(self, fill_mode):
        self._check_release_radar()

        # --- AUTO-BACKUP DB ---
        os.makedirs('data/backups', exist_ok=True)
        import shutil
        from datetime import datetime
        backup_name = f"data/backups/conveyor_state_{datetime.now().strftime('%Y%m%d')}.sqlite"
        if not os.path.exists(backup_name):
            try:
                shutil.copy2(self.db_path, backup_name)
                # Cleanup old backups (keep last 5)
                backups = sorted([os.path.join('data/backups', f) for f in os.listdir('data/backups') if f.endswith('.sqlite')])
                for old_b in backups[:-5]:
                    os.remove(old_b)
            except: pass
            
        logger.info(f"Iniciando ciclo del motor (fill_mode={fill_mode})")

        
        # 1. Sincronizador Inverso: Actualizar movimientos manuales antes de la purga
        self._sync_manual_moves()
        
        # 2. Limpiador de Fantasmas: Purgar archivos borrados manualmente
        self._clean_ghost_tracks()
        

        processed_listens, _ = self.telemetry.process_listens()
        logger.info(f"Nuevos scrobbles procesados: {processed_listens}")
        
        # --- BLINDAJE POR CORAZÓN (ListenBrainz Loved Tracks) ---
        loved_tracks = self.telemetry.get_loved_tracks()
        if loved_tracks:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, artist, title, file_path FROM tracks WHERE status IN ('CINTA', 'ANTOJO')")
                candidates = cursor.fetchall()
                
                from thefuzz import fuzz
                import shutil
                
                for l_artist, l_title in loved_tracks:
                    for c_id, c_artist, c_title, c_path in candidates:
                        if not c_path or not os.path.exists(c_path): continue
                        
                        if fuzz.token_set_ratio(l_artist.lower(), c_artist.lower()) > 80 and fuzz.token_set_ratio(l_title.lower(), c_title.lower()) > 85:
                            # Match found! Move to Permanente
                            target_dir = "storage/Permanente/Favorite Songs"
                            os.makedirs(target_dir, exist_ok=True)
                            new_path = os.path.join(target_dir, os.path.basename(c_path))
                            try:
                                shutil.move(c_path, new_path)
                                cursor.execute("UPDATE tracks SET status = 'PERMANENT', is_permanent = 1, file_path = ? WHERE id = ?", (new_path, c_id))
                                logger.info(f"¡Corazón detectado en ListenBrainz! Blindando en Permanente: {c_artist} - {c_title}")
                            except Exception as e:
                                logger.error(f"Fallo blindando por corazón {c_id}: {e}")
                            break

        
        with sqlite3.connect(self.db_path) as conn:
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
            # Ordenamos aleatoriamente para que si hay un error de red al inicio, no castigue siempre a la misma pista
            cursor.execute("SELECT id, artist, title, attempts FROM orphan_scrobbles ORDER BY RANDOM()")
            orphans_db = cursor.fetchall()
            
        if orphans_db:
            logger.info(f"Procesando {len(orphans_db)} scrobbles huérfanos pendientes...")
            
            # Procesar fuera de un bloque 'with conn' global para evitar SQLite 'database is locked'
            for row in orphans_db:
                o_id, artist, title, attempts = row
                rec = TrackRecommendation(
                    title=title, 
                    artist=artist, 
                    genre_context="Variado",
                    discovery_type="adjacent",
                    reason="Detectado en ListenBrainz"
                )
                
                # Validar de uno en uno para tener control granular de fallos
                val_count = self.curator.validate_and_save([rec])
                
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    if val_count > 0:
                        cursor.execute("DELETE FROM orphan_scrobbles WHERE id = ?", (o_id,))
                        logger.info(f"Scrobble huérfano procesado con éxito: {artist} - {title}")
                    else:
                        # Si falló (red, duplicado o no encontrado), sumamos un intento
                        cursor.execute("UPDATE orphan_scrobbles SET attempts = attempts + 1 WHERE id = ?", (o_id,))
                        
                    # Purgar los que hayan fallado 2 veces (evita bucles infinitos por canciones que no existen)
                    cursor.execute("DELETE FROM orphan_scrobbles WHERE attempts >= 2")
                    conn.commit()
            
        antojos_path = 'storage/antojos.txt'
        if os.path.exists(antojos_path):
            try:
                with open(antojos_path, 'r', encoding='utf-8') as f:
                    antojos_text = f.read().strip()
                if antojos_text:
                    if antojos_text.lower().startswith('radio:'):
                        vibra = antojos_text[6:].strip()
                        logger.info(f"Modo Radio Local activado para: '{vibra}'")
                        self.curator.generate_local_radio(vibra)
                        open(antojos_path, 'w').close()
                    else:
                        logger.info(f"Archivo de antojos detectado. Procesando intención: '{antojos_text[:50]}...'")
                        intent_groups = self.curator.run_intent_curation(antojos_text)
                        if intent_groups is not None:
                            if intent_groups:
                                val_intent = 0
                                for group in intent_groups:
                                    target_f = f"Antojos/{group.folder_name}"
                                    os.makedirs(f"storage/{target_f}", exist_ok=True)
                                    val_intent += self.curator.validate_and_save(group.tracks, target_folder=target_f, target_status="PENDING_ANTOJO")
                                logger.info(f"Pistas de antojo validadas e insertadas: {val_intent}")
                            
                            # Vaciar el archivo en lugar de borrarlo para que el usuario pueda reutilizarlo
                            open(antojos_path, 'w').close()
                        else:
                            logger.warning("No se eliminó el archivo de antojos debido a un error del LLM (ej. cuota excedida).")
            except Exception as e:
                logger.error(f"Error procesando archivo de antojos: {e}")
        
        is_fresh = self.telemetry.is_telemetry_fresh()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            promo_count = self.conveyor_config.get('promotion_play_count', 15)
            cursor.execute("SELECT id, file_path FROM tracks WHERE status IN ('CINTA', 'ANTOJO') AND play_count >= ?", (promo_count,))
            to_promote = cursor.fetchall()
            
            promo_dir = "storage/Permanente/Descubrimientos_Favoritos"
            os.makedirs(promo_dir, exist_ok=True)
            
            for t_id, f_path in to_promote:
                filename = os.path.basename(f_path)
                new_path = os.path.join(promo_dir, filename)
                
                try:
                    if os.path.exists(f_path):
                        shutil.move(f_path, new_path)
                    
                    cursor.execute("""
                        UPDATE tracks 
                        SET status = 'PERMANENT', is_permanent = 1, file_path = ?
                        WHERE id = ?
                    """, (new_path, t_id))
                    logger.info(f"Promocionado {t_id} a {new_path}")
                except Exception as e:
                    logger.error(f"Fallo promocionando {t_id}: {e}")
                    
            if not is_fresh:
                logger.warning("Telemetría desactualizada. Omitiendo fase de purga.")
            else:
                grace_days = self.conveyor_config.get('grace_period_days', 30)
                cursor.execute(f"""
                    SELECT id, file_path FROM tracks 
                    WHERE status = 'CINTA' 
                    AND (julianday('now') - julianday(COALESCE(last_played_at, added_at))) > ?
                """, (grace_days,))
                to_purge_time = cursor.fetchall()
                
                cursor.execute(f"""
                    SELECT id, file_path FROM tracks
                    WHERE status IN ('CINTA', 'ANTOJO')
                    AND skip_count >= 5
                """)
                to_purge_skip = cursor.fetchall()
                
                to_purge = list(set(to_purge_time + to_purge_skip))
                
                # --- PURGA DE ANTOJOS (POR CARPETA) ---
                cursor.execute("SELECT id, file_path FROM tracks WHERE status = 'ANTOJO'")
                antojo_tracks = cursor.fetchall()
                antojo_folders = {}
                for t_id, f_path in antojo_tracks:
                    if f_path:
                        folder = os.path.dirname(f_path)
                        if folder not in antojo_folders:
                            antojo_folders[folder] = []
                        antojo_folders[folder].append((t_id, f_path))
                
                for folder, tracks in antojo_folders.items():
                    t_ids = [t[0] for t in tracks]
                    placeholders = ','.join('?' * len(t_ids))
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM tracks 
                        WHERE id IN ({placeholders}) 
                        AND (julianday('now') - julianday(COALESCE(last_played_at, added_at))) <= ?
                    """, (*t_ids, grace_days))
                    active_in_folder = cursor.fetchone()[0]
                    
                    if active_in_folder == 0:
                        logger.info(f"Purgando carpeta de Antojos inactiva: {folder}")
                        to_purge.extend(tracks)
                        import shutil
                        if os.path.exists(folder):
                            try:
                                shutil.rmtree(folder)
                            except: pass
                
                for t_id, f_path in to_purge:
                    try:
                        if os.path.exists(f_path):
                            os.remove(f_path)
                            
                        new_status = 'ARCHIVED' if (f_path and 'Antojos' in f_path) else 'PURGED'
                        cursor.execute("UPDATE tracks SET status = ? WHERE id = ?", (new_status, t_id))
                        logger.info(f"Purgado {t_id} ({f_path}) a estado {new_status}")
                    except Exception as e:
                        logger.error(f"Fallo purgando {t_id}: {e}")
            
            conn.commit()
            
            import time
            total_downloaded = 0
            
            while True:
                cursor.execute("SELECT COUNT(*) FROM tracks WHERE status = 'CINTA' OR (status = 'PENDING' AND is_permanent = 0)")
                active_count = cursor.fetchone()[0]
                
                target_buffer = self.conveyor_config.get('buffer_size', 750)
                slots = target_buffer - active_count
                
                if slots > 0:
                    logger.info(f"Rellenando {slots} huecos libres en la Cinta")
                    validated = self.curator.run_curation_cycle(slots)
                    logger.info(f"Curador LLM proporcionó {validated} nuevas pistas")
                    if validated == 0 and fill_mode:
                        logger.warning("El curador devolvió 0 pistas. Abortando modo fill para evitar bucle infinito.")
                        fill_mode = False
                
                cursor.execute("SELECT COUNT(*) FROM tracks WHERE status IN ('PENDING', 'PENDING_ANTOJO')")
                remaining = cursor.fetchone()[0]
                
                if remaining == 0:
                    if fill_mode and slots > 0:
                        logger.info("Aún hay huecos, continuando el bucle de llenado (fill_mode)...")
                        continue
                    else:
                        break
                        
                logger.info(f"Quedan {remaining} pistas PENDING en cola. Iniciando lote de descargas...")
                downloaded = self.downloader.download_pending_tracks()
                total_downloaded += downloaded
                
                cursor.execute("SELECT COUNT(*) FROM tracks WHERE status IN ('PENDING', 'PENDING_ANTOJO')")
                new_remaining = cursor.fetchone()[0]
                logger.info(f"Lote completado. Descargadas: {downloaded} | Restantes en cola: {new_remaining}")
                
                if new_remaining > 0 or (fill_mode and slots - downloaded > 0):
                    logger.info("Pausando 10 segundos antes del siguiente lote/ciclo para evitar rate-limits...")
                    time.sleep(10)
                    
            logger.info(f"Cola de descargas vaciada. Total descargado en el ciclo: {total_downloaded}")
            
        self._process_local_file_ratings()
        self._check_auto_antojos()
        self.playlists.update_all_playlists()
        logger.info("Ciclo del motor completado con éxito")
