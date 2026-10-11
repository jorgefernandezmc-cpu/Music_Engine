import os
import sqlite3
import logging
import math
import yaml
import re
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from ytmusicapi import YTMusic
from thefuzz import fuzz

os.makedirs('logs', exist_ok=True)
logger = logging.getLogger('curator')
if not logger.handlers:
    fh = logging.FileHandler('logs/curator.log')
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(fh)
    logger.setLevel(logging.INFO)

class TrackRecommendation(BaseModel):
    artist: str = Field(description="Nombre del artista")
    title: str = Field(description="Título de la canción")
    genre_context: str = Field(description="OBLIGATORIO elegir UNO de estos exactos: 'Urbano', 'Hip-Hop/Rap', 'Pop & Indie', 'Electrónica', 'Rock', 'R&B / Soul', 'Tropical & Raíces', 'Soundtracks', 'Variado'. REGLA CRÍTICA: El género 'Urbano' tiene PRIORIDAD ABSOLUTA. Si una canción (por ejemplo de Rauw Alejandro, Mora, etc.) está en la frontera entre Urbano y R&B/Soul o Tropical, DEBE ser clasificada como 'Urbano'.")
    discovery_type: str = Field(description="Debe ser exactamente uno de: exploitation, adjacent, exploration")
    reason: str = Field(description="Breve justificación de por qué encaja en los gustos del usuario")

class RecommendationList(BaseModel):
    tracks: list[TrackRecommendation]

class IntentAction(BaseModel):
    action_type: str = Field(description="OBLIGATORIO: Uno de 'artist_hits', 'album_tracks', o 'playlist_vibe'")
    search_query: str = Field(description="Término exacto de búsqueda para YouTube Music (ej. 'Daniela Garsal' o 'La Jauría Dani Fernández')")
    folder_name: str = Field(description="Nombre de la carpeta para agrupar estas pistas (ej. Daniela_Garsal_Hits)")
    limit: int = Field(description="Cantidad máxima de pistas a extraer (ej. 20 para hits, 40 para playlists)")
    genre_context: str = Field(description="OBLIGATORIO elegir UNO de estos exactos: 'Urbano', 'Hip-Hop/Rap', 'Pop & Indie', 'Electrónica', 'Rock', 'R&B / Soul', 'Tropical & Raíces', 'Soundtracks', 'Variado'")

class IntentActionList(BaseModel):
    actions: list[IntentAction]

class AntojoGroup(BaseModel):
    folder_name: str = Field(description="Nombre de subcarpeta sin espacios (ej. Bad_Bunny_Ultimo_Album)")
    tracks: list[TrackRecommendation]

class IntentRecommendationList(BaseModel):
    groups: list[AntojoGroup]

class CuratorLLM:
    def __init__(self, db_path: str, config_path: str = "config/config.yaml"):
        self.db_path = db_path
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
            
        from dotenv import load_dotenv
        env_path = os.path.join(os.path.dirname(config_path), '.env')
        load_dotenv(env_path)
            
        api_key = os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=api_key) if api_key and "your_" not in api_key else None
        self.model_name = self.config.get('llm', {}).get('model', 'gemini-3.6-flash')
        self.max_api_calls = 18 # Límite por ejecución para guardar peticiones para "antojos"
        self.api_calls_made = 0
        self.weights = self.config.get('llm', {}).get('diversity_weights', {
            'exploitation': 0.60, 'adjacent': 0.25, 'exploration': 0.15
        })
        self.yt = YTMusic()
        
    def sanitize_filename(self, name: str) -> str:
        if not name: return "Unknown"
        name = re.sub(r'[/\\:*?"<>|]', '-', name)
        return name.strip('. ')

    def _get_context(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT artist, SUM(play_count) as total 
                FROM tracks 
                GROUP BY artist 
                ORDER BY total DESC LIMIT 10
            """)
            top_historico = [row[0] for row in cursor.fetchall()]
            
            cursor.execute("""
                SELECT artist FROM tracks 
                WHERE play_count > 0 
                ORDER BY RANDOM() LIMIT 10
            """)
            top_reciente = [row[0] for row in cursor.fetchall()]
            
        return top_historico, top_reciente

    def _get_seeds(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Conservative (High plays)
            cursor.execute("SELECT id, artist, title FROM tracks WHERE play_count >= 5 ORDER BY RANDOM() LIMIT 2")
            cons_seeds = cursor.fetchall()
            
            # Medium (1-4 plays)
            cursor.execute("SELECT id, artist, title FROM tracks WHERE play_count BETWEEN 1 AND 4 ORDER BY RANDOM() LIMIT 1")
            med_seeds = cursor.fetchall()
            
            # Exploration (0 plays, or lowest 20% artists)
            cursor.execute("""
                SELECT id, artist, title FROM tracks 
                WHERE play_count = 0 AND status IN ('CINTA', 'PERMANENT') 
                ORDER BY RANDOM() LIMIT 1
            """)
            exp_seeds = cursor.fetchall()
            
            # Fallbacks
            if not cons_seeds:
                cursor.execute("SELECT id, artist, title FROM tracks ORDER BY RANDOM() LIMIT 2")
                cons_seeds = cursor.fetchall()
            if not med_seeds:
                cursor.execute("SELECT id, artist, title FROM tracks ORDER BY RANDOM() LIMIT 1")
                med_seeds = cursor.fetchall()
            if not exp_seeds:
                cursor.execute("SELECT id, artist, title FROM tracks ORDER BY RANDOM() LIMIT 1")
                exp_seeds = cursor.fetchall()
                
            return cons_seeds + med_seeds + exp_seeds

    def generate_recommendations(self, slots_needed: int) -> list[TrackRecommendation]:
        if not self.client:
            logger.warning("Gemini no configurado.")
            return []
            
        if self.api_calls_made >= self.max_api_calls:
            logger.warning(f"Límite de seguridad alcanzado ({self.max_api_calls} peticiones a Gemini).")
            return []
            
        seeds = self._get_seeds()
        if not seeds:
            logger.warning("No hay semillas en BD.")
            return []
            
        candidates = []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM tracks")
            existing_ids = {row[0] for row in cursor.fetchall()}
            
        import random
        
        for seed_id, s_artist, s_title in seeds:
            try:
                radio = self.yt.get_watch_playlist(videoId=seed_id, limit=25)
                if 'tracks' in radio:
                    for t in radio['tracks']:
                        vid = t.get('videoId')
                        if vid and vid not in existing_ids:
                            candidates.append({
                                'id': vid,
                                'title': t.get('title', ''),
                                'artist': t.get('artists', [{'name': ''}])[0].get('name', ''),
                                'seed_context': f"Radio de {s_artist} - {s_title}"
                            })
                            existing_ids.add(vid)
            except Exception as e:
                logger.error(f"Error extrayendo radio YTM para {seed_id}: {e}")
                
        if not candidates:
            logger.warning("YTMusic no devolvió candidatos válidos.")
            return []
            
        random.shuffle(candidates)
        candidates = candidates[:80]
        
        top_hist, top_rec = self._get_context()
        
        candidate_text = "\n".join([f"[{i}] {c['artist']} - {c['title']} (Origen: {c['seed_context']})" for i, c in enumerate(candidates)])
        
        prompt = f"""
        Actúa como un curador musical profesional. Aquí tienes {len(candidates)} canciones obtenidas de radios relacionadas con la base del usuario.
        
        PERFIL DEL USUARIO:
        Artistas Top Históricos: {', '.join(top_hist) if top_hist else 'Desconocido'}
        Artistas en Rotación Reciente: {', '.join(top_rec) if top_rec else 'Desconocido'}
        
        INSTRUCCIONES ESTRICTAS:
        1. Analiza cada una de las canciones candidatas listadas abajo.
        2. Puntúa internamente (del 0 al 100) cómo encajan con el perfil del usuario.
        3. DESCARTA toda la basura hiper-comercial genérica que no encaje, o canciones que se alejen demasiado de su estilo (salvo que sea para exploración controlada).
        4. DEVUELVE ÚNICAMENTE las canciones que superen los 85 puntos de calidad y afinidad.
        5. Para cada canción que apruebes, mantén EXACTAMENTE el mismo Artista y Título.
        
        CANDIDATOS:
        {candidate_text}
        
        Devuelve SOLO JSON válido cumpliendo el esquema solicitado.
        """
        
        self.api_calls_made += 1
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=RecommendationList,
                ),
            )
            parsed = response.parsed
            if hasattr(parsed, 'tracks'):
                tracks = parsed.tracks
            else:
                import json
                data = json.loads(response.text)
                tracks = [TrackRecommendation(**t) for t in data.get('tracks', [])]
                
            logger.info(f"Curador Híbrido (Pro) filtró {len(candidates)} candidatos y aprobó {len(tracks)} pistas estelares.")
            return tracks
            
        except Exception as e:
            logger.error(f"Error generando o parseando recomendaciones del LLM: {e}")
            import time
            time.sleep(15) # Evitar ametrallar a la API si nos da un 429
            return []


    def validate_and_save(self, candidates: list[TrackRecommendation], target_folder: str = "Cinta", target_status: str = "PENDING") -> int:
        valid_count = 0
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for rec in candidates:
                query = f"{rec.artist} {rec.title}"
                try:
                    search_results = self.yt.search(query, filter="songs", limit=1)
                except Exception as e:
                    logger.error(f"Error en búsqueda YT para '{query}': {e}")
                    continue
                    
                if not search_results:
                    logger.info(f"Descartado '{query}': No encontrado en YouTube Music")
                    continue
                    
                top_result = search_results[0]
                r_title = top_result.get('title', '')
                r_artist = top_result.get('artists', [{'name': ''}])[0].get('name', '')
                
                sim = fuzz.token_set_ratio(query.lower(), f"{r_artist} {r_title}".lower())
                if sim < 80:
                    logger.info(f"Descartado '{query}': Similitud insuficiente ({sim}%) contra '{r_artist.lower()} {r_title.lower()}'")
                    continue
                    
                vid = top_result.get('videoId')
                if not vid:
                    continue
                    
                r_album = top_result.get('album', {}).get('name') if top_result.get('album') else None
                r_duration = top_result.get('duration_seconds', 0)
                
                safe_title = self.sanitize_filename(r_title)
                safe_artist = self.sanitize_filename(r_artist)
                file_path = f"storage/{target_folder}/{safe_artist} - {safe_title}.opus"
                
                # Check if file_path (case-insensitive) already exists to prevent Android Syncthing conflicts
                cursor.execute("SELECT id FROM tracks WHERE LOWER(file_path) = LOWER(?)", (file_path,))
                dup_row = cursor.fetchone()
                if dup_row and dup_row[0] != vid:
                    logger.info(f"Descartado '{query}': Ya existe un archivo casi idéntico en la BD (ID: {dup_row[0]}). Evitando conflicto de sincronización en Android.")
                    continue

                cursor.execute("SELECT status, file_path FROM tracks WHERE id = ?", (vid,))
                row = cursor.fetchone()
                if row:
                    current_status = row[0]
                    current_path = row[1]
                    
                    if current_status == 'ARCHIVED':
                        logger.info(f"Resucitando pista archivada '{query}' (ID: {vid})")
                        cursor.execute("""
                            UPDATE tracks 
                            SET status = ?, file_path = ?, is_permanent = 0
                            WHERE id = ?
                        """, (target_status, file_path, vid))
                        valid_count += 1
                    elif target_status == 'PENDING_ANTOJO':
                        import shutil
                        import os
                        import uuid
                        new_vid = f"{vid}_{uuid.uuid4().hex[:6]}"
                        logger.info(f"Duplicando pista para ANTOJO: '{query}' (Original ID: {vid}, Nuevo ID: {new_vid})")
                        
                        if current_path and os.path.exists(current_path):
                            try:
                                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                                shutil.copy(current_path, file_path)
                                
                                cursor.execute("""
                                    INSERT INTO tracks (id, title, artist, album, duration_seconds, status, is_permanent, file_path, genre)
                                    VALUES (?, ?, ?, ?, ?, 'ANTOJO', 0, ?, ?)
                                """, (new_vid, r_title, r_artist, r_album, r_duration, file_path, rec.genre_context))
                                valid_count += 1
                                logger.info(f"Copiado localmente con éxito para antojo.")
                            except Exception as e:
                                logger.error(f"Error copiando archivo a Antojos: {e}")
                        else:
                            # If file doesn't exist locally, just download it as new
                            cursor.execute("""
                                INSERT INTO tracks (id, title, artist, album, duration_seconds, status, is_permanent, file_path, genre)
                                VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                            """, (new_vid, r_title, r_artist, r_album, r_duration, target_status, file_path, rec.genre_context))
                            valid_count += 1
                    else:
                        logger.info(f"Descartado '{query}': Ya existe en la BD (estado: {current_status}, ID: {vid})")
                    continue
                    
                cursor.execute("""
                    INSERT INTO tracks (id, title, artist, album, duration_seconds, status, is_permanent, file_path, genre)
                    VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                """, (vid, r_title, r_artist, r_album, r_duration, target_status, file_path, rec.genre_context))
                
                logger.info(f"Aceptado '{query}' -> YT: '{r_artist.lower()} {r_title.lower()}' (Similitud: {sim}%) [ID: {vid}]")
                valid_count += 1
                
        return valid_count

    def run_intent_curation(self, intent_text: str) -> list[AntojoGroup]:
        if not self.client:
            logger.warning("Gemini no configurado para curación de antojos.")
            return []
            
        prompt = f"""
        Actúa como un recomendador musical inteligente. Traduce esta intención del usuario en COMANDOS DE BÚSQUEDA (IntentAction).
        Ya no debes adivinar ni inventar canciones. Solo debes indicar qué y cómo debemos buscar en YouTube Music.
        
        REGLAS:
        - action_type: Usa 'artist_hits' si pide canciones de un artista. Usa 'album_tracks' si pide un álbum concreto. Usa 'playlist_vibe' si pide una vibra genérica o un género (ej. 'reggaeton', 'estudiar').
        - search_query: Sé preciso. Si es un álbum, incluye el nombre del álbum y del artista.
        - limit: Para álbumes ignoraremos este límite, pero para artist_hits o playlist_vibe pon al menos 20.
        
        INTENCIÓN DEL USUARIO:
        '{intent_text}'
        
        Devuelve SOLO JSON válido cumpliendo el esquema solicitado (IntentActionList).
        """
        
        self.api_calls_made += 1
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=IntentActionList,
                ),
            )
            
            actions = []
            parsed = response.parsed
            if parsed is not None:
                actions = parsed.actions
            else:
                import json
                data = json.loads(response.text)
                actions = [IntentAction(**a) for a in data.get('actions', [])]
                
            logger.info(f"LLM generó {len(actions)} intenciones de búsqueda RAG.")
            
            return self._execute_rag_actions(actions)

            
        except Exception as e:
            logger.error(f"Error procesando el antojo del usuario con LLM/RAG: {e}")
            return []



    def _execute_rag_actions(self, actions) -> list[AntojoGroup]:
        final_groups = []
        for action in actions:
            logger.info(f"Ejecutando RAG ({action.action_type}): '{action.search_query}'")
            extracted_tracks = []
            
            try:
                if action.action_type == 'artist_hits':
                    songs = self.yt.search(action.search_query, filter="songs", limit=action.limit)
                    for s in songs:
                        title = s.get('title', '')
                        artist = s.get('artists', [{'name': ''}])[0].get('name', '') if s.get('artists') else 'Unknown'
                        if title and artist:
                            extracted_tracks.append((title, artist))
                            
                elif action.action_type == 'album_tracks':
                    albums = self.yt.search(action.search_query, filter="albums", limit=1)
                    if albums:
                        album_id = albums[0].get('browseId')
                        if album_id:
                            album_data = self.yt.get_album(album_id)
                            for t in album_data.get('tracks', []):
                                title = t.get('title', '')
                                artist = t.get('artists', [{'name': ''}])[0].get('name', '') if t.get('artists') else 'Unknown'
                                if title and artist:
                                    extracted_tracks.append((title, artist))
                    if not extracted_tracks:
                        logger.warning("Álbum no encontrado, haciendo búsqueda fallback de canciones...")
                        songs = self.yt.search(action.search_query, filter="songs", limit=15)
                        for s in songs:
                            title = s.get('title', '')
                            artist = s.get('artists', [{'name': ''}])[0].get('name', '') if s.get('artists') else 'Unknown'
                            if title and artist:
                                extracted_tracks.append((title, artist))
                                
                elif action.action_type == 'playlist_vibe':
                    playlists = self.yt.search(action.search_query, filter="playlists", limit=1)
                    if playlists:
                        play_id = playlists[0].get('browseId')
                        if play_id:
                            try:
                                play_data = self.yt.get_playlist(play_id, limit=action.limit)
                                for t in play_data.get('tracks', []):
                                    title = t.get('title', '')
                                    artist = t.get('artists', [{'name': ''}])[0].get('name', '') if t.get('artists') else 'Unknown'
                                    if title and artist:
                                        extracted_tracks.append((title, artist))
                            except Exception as e:
                                logger.error(f"Error extrayendo tracks de playlist {play_id}: {e}")
            except Exception as e:
                logger.error(f"Error en ytmusicapi durante RAG: {e}")
                
            if extracted_tracks:
                logger.info(f"RAG extrajo {len(extracted_tracks)} canciones de YouTube Music.")
                seen = set()
                unique_tracks = []
                for title, artist in extracted_tracks:
                    k = f"{artist.lower()} - {title.lower()}"
                    if k not in seen:
                        seen.add(k)
                        unique_tracks.append(
                            TrackRecommendation(
                                artist=artist,
                                title=title,
                                genre_context=action.genre_context,
                                discovery_type="adjacent",
                                reason=f"Extraído vía YT Music ({action.action_type})"
                            )
                        )
                final_groups.append(AntojoGroup(folder_name=action.folder_name, tracks=unique_tracks))
                
        return final_groups

    def run_auto_antojo(self, artist_name: str, genre: str = "Variado") -> list[AntojoGroup]:
        logger.info(f"Generando Auto-Antojo para: {artist_name}")
        action = IntentAction(
            action_type="artist_hits",
            search_query=artist_name,
            folder_name=f"{artist_name.replace(' ', '_')}_Sorpresa",
            limit=15,
            genre_context=genre
        )
        return self._execute_rag_actions([action])

    def generate_local_radio(self, vibra: str) -> None:
        if not self.client:
            return
            
        logger.info(f"Generando Radio Local para vibra: '{vibra}'")
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, artist, title, file_path FROM tracks WHERE status IN ('CINTA', 'PERMANENT', 'ANTOJO')")
            all_tracks = cursor.fetchall()
            
        if not all_tracks:
            return
            
        prompt = f"""
        Actúa como un DJ. El usuario quiere una radio local con esta vibra: '{vibra}'.
        Aquí tienes las canciones disponibles en su dispositivo.
        Elige las 40 canciones que MEJOR encajen con esta vibra.
        Devuelve SOLO un JSON con una lista de IDs.
        
        CANCIONES:
        """
        for t_id, t_artist, t_title, _ in all_tracks:
            prompt += f"[{t_id}] {t_artist} - {t_title}\n"
            
        class RadioSelection(BaseModel):
            ids: list[str]
            
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=RadioSelection,
                ),
            )
            parsed = response.parsed
            if hasattr(parsed, 'ids'):
                selected_ids = parsed.ids
            else:
                import json
                data = json.loads(response.text)
                selected_ids = data.get('ids', [])
                
            import os
            os.makedirs("storage/Playlists", exist_ok=True)
            m3u8_path = f"storage/Playlists/Radio_{self.sanitize_filename(vibra)}.m3u8"
            
            with open(m3u8_path, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
                for t_id in selected_ids:
                    f_path = next((t[3] for t in all_tracks if t[0] == t_id), None)
                    if f_path and os.path.exists(f_path):
                        rel_path = os.path.relpath(f_path, "storage/Playlists")
                        f.write(f"{rel_path}\n")
                        
            logger.info(f"Radio local generada: {m3u8_path} con {len(selected_ids)} canciones.")
            
        except Exception as e:
            logger.error(f"Error generando radio local: {e}")

    def run_curation_cycle(self, slots: int) -> int:
        """Bucle principal de curación que itera hasta rellenar los slots o agotar intentos."""
        total_validated = 0
        
        batch_size = 50
        max_attempts = int(slots / batch_size) + 5
        attempts = 0
        
        while total_validated < slots and attempts < max_attempts:
            needed = slots - total_validated
            logger.info(f"Solicitando {needed} recomendaciones al LLM (Intento {attempts+1}/{max_attempts})")
            
            candidates = self.generate_recommendations(needed)
            if not candidates:
                attempts += 1
                import time
                time.sleep(15) # Evitar ametrallar a la API si nos da un 429 por límite de peticiones por minuto
                continue
                
            validated = self.validate_and_save(candidates)
            total_validated += validated
            attempts += 1
            
        return total_validated
