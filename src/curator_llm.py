import os
import logging
import math
import yaml
import re
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from ytmusicapi import YTMusic
from thefuzz import fuzz
from src.paths import StoragePaths, sanitize_filename
from src.album_resolver import resolve_album_track
from src.db import get_db_connection

os.makedirs('logs', exist_ok=True)
logger = logging.getLogger('curator')
if not logger.handlers:
    fh = logging.FileHandler('logs/curator.log')
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(fh)
    logger.setLevel(logging.INFO)

class TrackRecommendation(BaseModel):
    artist: str = Field(description="Artist name")
    title: str = Field(description="Song title")
    genre_context: str = Field(description="Precise, standard music genre(s) for the track, separated by ' / ' if multiple (e.g. 'Reggaeton / Trap Latino', 'Indie Rock / Pop', 'Rock', 'Pop / R&B', 'Electronic / House', 'Hip-Hop / Rap'). Must be accurate and descriptive.")
    discovery_type: str = Field(description="Must be exactly one of: exploitation, adjacent, exploration")
    reason: str = Field(description="Brief justification of why it matches the user's taste")

class RecommendationList(BaseModel):
    tracks: list[TrackRecommendation]

class IntentAction(BaseModel):
    action_type: str = Field(description="MANDATORY: One of 'track', 'artist_hits', 'album_tracks', or 'playlist_vibe'")
    search_query: str = Field(description="Exact search query for YouTube Music (e.g. 'Quevedo Columbia', 'Daniela Garsal' or 'La Jauria Dani Fernandez')")
    folder_name: str = Field(description="Folder name to group these tracks (e.g. Favorites, Daniela_Garsal_Hits)")
    limit: int = Field(description="Maximum tracks to extract (e.g. 20 for hits, 40 for playlists)")
    genre_context: str = Field(description="Precise music genre(s) for the request separated by ' / ' if applicable (e.g. 'Reggaeton / Trap Latino', 'Indie Rock / Pop', 'Rock', etc.)")

class IntentActionList(BaseModel):
    actions: list[IntentAction]

class RequestGroup(BaseModel):
    folder_name: str = Field(description="Descriptive name for the request (e.g. Favorites, Rock_Espanol)")
    tracks: list[TrackRecommendation]

PeticionGroup = RequestGroup
AntojoGroup = RequestGroup

class IntentRecommendationList(BaseModel):
    groups: list[RequestGroup]

class CuratorLLM:
    def __init__(self, db_path: str, config_path: str = "config/config.yaml"):
        self.db_path = db_path
        self.paths = StoragePaths(config_path)
        self.paths.ensure_dirs()
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
            
        from dotenv import load_dotenv
        env_path = os.path.join(os.path.dirname(config_path), '.env')
        load_dotenv(env_path)
            
        api_key = os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=api_key) if api_key and "your_" not in api_key else None
        self.model_name = self.config.get('llm', {}).get('model', 'gemini-3.5-flash')
        self.max_api_calls = 18 # Per-run safety limit to protect quota
        self.api_calls_made = 0
        self.weights = self.config.get('llm', {}).get('diversity_weights', {
            'exploitation': 0.60, 'adjacent': 0.25, 'exploration': 0.15
        })
        self.yt = YTMusic()
        
    def sanitize_filename(self, name: str) -> str:
        return sanitize_filename(name)

    def _get_context(self):
        with get_db_connection(self.db_path) as conn:
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
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Conservative (High plays)
            cursor.execute("SELECT id, artist, title FROM tracks WHERE play_count >= 5 ORDER BY RANDOM() LIMIT 2")
            cons_seeds = cursor.fetchall()
            
            # Medium (1-4 plays)
            cursor.execute("SELECT id, artist, title FROM tracks WHERE play_count BETWEEN 1 AND 4 ORDER BY RANDOM() LIMIT 1")
            med_seeds = cursor.fetchall()
            
            # Exploration (0 plays, or lower 20% artists)
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
            logger.warning("Gemini not configured.")
            return []
            
        if self.api_calls_made >= self.max_api_calls:
            logger.warning(f"Safety limit reached ({self.max_api_calls} requests to Gemini).")
            return []
            
        seeds = self._get_seeds()
        if not seeds:
            logger.warning("No seeds found in DB.")
            return []
            
        candidates = []
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM tracks")
            existing_ids = {row[0] for row in cursor.fetchall()}
            
        import random
        
        for seed_id, s_artist, s_title in seeds:
            clean_seed_id = seed_id.split('_')[0] if seed_id else ''
            try:
                radio = self.yt.get_watch_playlist(videoId=clean_seed_id, limit=25)
                if 'tracks' in radio:
                    for t in radio['tracks']:
                        vid = t.get('videoId')
                        if vid and vid not in existing_ids:
                            candidates.append({
                                'id': vid,
                                'title': t.get('title', ''),
                                'artist': t.get('artists', [{'name': ''}])[0].get('name', ''),
                                'seed_context': f"Radio of {s_artist} - {s_title}"
                            })
                            existing_ids.add(vid)
            except Exception as e:
                logger.error(f"Error extracting YTM radio for {seed_id}: {e}")
                
        if not candidates:
            logger.warning("YTMusic did not return valid candidates.")
            return []
            
        random.shuffle(candidates)
        candidates = candidates[:80]
        
        top_hist, top_rec = self._get_context()
        
        candidate_text = "\n".join([f"[{i}] {c['artist']} - {c['title']} (Origin: {c['seed_context']})" for i, c in enumerate(candidates)])
        
        prompt = f"""
        Act as a professional music curator. Here are {len(candidates)} candidate tracks retrieved from radios related to the user's taste base.
        
        USER TASTE PROFILE:
        Top Historic Artists: {', '.join(top_hist) if top_hist else 'Unknown'}
        Artists in Recent Rotation: {', '.join(top_rec) if top_rec else 'Unknown'}
        
        STRICT INSTRUCTIONS:
        1. Analyze each candidate track listed below.
        2. Internally score (from 0 to 100) how well each track fits the user's taste profile.
        3. DISCARD all generic hyper-commercial filler that doesn't fit, or songs deviating too far from their style (unless suitable for controlled exploration).
        4. RETURN ONLY songs that exceed 85 points in quality and affinity.
        5. For each approved song, keep EXACTLY the same Artist and Title.
        
        CANDIDATES:
        {candidate_text}
        
        Return ONLY valid JSON complying with the requested schema.
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
                
            logger.info(f"Hybrid Curator filtered {len(candidates)} candidates and approved {len(tracks)} stellar tracks.")
            return tracks
            
        except Exception as e:
            logger.error(f"Error generating or parsing LLM recommendations: {e}")
            import time
            time.sleep(15) # Avoid hammering API if rate limited
            return []

    def validate_and_save(self, candidates: list[TrackRecommendation], target_folder: str = "Cinta", target_status: str = "PENDING") -> int:
        valid_count = 0
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            for rec in candidates:
                # Prioritize album version
                resolved = resolve_album_track(self.yt, rec.artist, rec.title)
                vid = resolved.get('id')
                if not vid:
                    logger.info(f"Discarded '{rec.artist} - {rec.title}': Not found on YouTube Music")
                    continue
                    
                r_title = resolved['title']
                r_artist = resolved['artist']
                r_primary_artist = resolved.get('primary_artist', r_artist)
                r_album = resolved['album']
                r_duration = resolved['duration_seconds']
                
                safe_title = self.sanitize_filename(r_title)
                safe_artist = self.sanitize_filename(r_primary_artist)
                safe_album = self.sanitize_filename(r_album)
                
                if target_folder in ("Cinta", "Conveyor"):
                    file_path = self.paths.get_cinta_track_path(safe_artist, safe_title)
                    is_perm = 0
                    # STRICT RULE: Never download to Conveyor tracks already present in Permanent
                    cursor.execute("SELECT id FROM tracks WHERE status = 'PERMANENT' AND (LOWER(title) = LOWER(?) OR LOWER(id) = LOWER(?))", (r_title, vid))
                    if cursor.fetchone():
                        logger.info(f"Discarded for Conveyor '{r_artist} - {r_title}': Already exists in Permanent.")
                        continue
                elif target_folder in ("Cravings", "Antojos"):
                    file_path = self.paths.get_craving_track_path(safe_artist, safe_album, safe_title)
                    is_perm = 0
                else:
                    file_path = self.paths.get_permanente_track_path(safe_artist, safe_album, safe_title)
                    is_perm = 1
                
                # Check if file_path (case-insensitive) already exists to prevent Android Syncthing conflicts
                cursor.execute("SELECT id FROM tracks WHERE LOWER(file_path) = LOWER(?)", (file_path,))
                dup_row = cursor.fetchone()
                if dup_row and dup_row[0] != vid:
                    logger.info(f"Discarded '{rec.artist} - {rec.title}': Near-identical file already in DB (ID: {dup_row[0]}). Preventing Android sync conflict.")
                    continue

                cursor.execute("SELECT status, file_path FROM tracks WHERE id = ?", (vid,))
                row = cursor.fetchone()
                if row:
                    current_status = row[0]
                    current_path = row[1]
                    
                    if current_status == 'ARCHIVED':
                        logger.info(f"Resurrecting archived track '{rec.artist} - {rec.title}' (ID: {vid})")
                        cursor.execute("""
                            UPDATE tracks 
                            SET status = ?, file_path = ?, is_permanent = ?, album = ?
                            WHERE id = ?
                        """, (target_status, file_path, is_perm, r_album, vid))
                        valid_count += 1
                    else:
                        logger.info(f"Discarded '{rec.artist} - {rec.title}': Already exists in DB (status: {current_status}, ID: {vid})")
                    continue
                    
                r_track_num = resolved.get('track_number')
                r_rel_date = resolved.get('release_date')
                cursor.execute("""
                    INSERT INTO tracks (id, title, artist, album, duration_seconds, status, is_permanent, file_path, genre, track_number, release_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (vid, r_title, r_artist, r_album, r_duration, target_status, is_perm, file_path, rec.genre_context, r_track_num, r_rel_date))
                
                logger.info(f"Accepted '{r_artist} - {r_title}' [Album: {r_album}] [ID: {vid}]")
                valid_count += 1
                
        return valid_count

    def run_intent_curation(self, intent_text: str) -> list[RequestGroup]:
        if not self.client:
            logger.warning("Gemini not configured for request curation.")
            return []
            
        prompt = f"""
        Act as an intelligent music recommender. Translate the user's intent into SEARCH COMMANDS (IntentAction).
        Do not guess or hallucinate songs. Only specify what and how to search on YouTube Music.
        
        RULES:
        - action_type:
          * Use 'track' if the user asks for one or more exact specific songs (e.g. 'Quevedo - Columbia', 'La Nasa by Anther').
          * Use 'artist_hits' if asking for tracks by an artist.
          * Use 'album_tracks' if asking for a specific album.
          * Use 'playlist_vibe' if asking for a general vibe or genre (e.g. 'reggaeton', 'study').
        - search_query: Be ultra precise. If a song or album, include official artist and title.
        - limit: 1 for individual songs ('track'), for albums the total track count, for artist_hits or playlist_vibe use at least 20.
        
        USER INTENT:
        '{intent_text}'
        
        Return ONLY valid JSON complying with the requested schema (IntentActionList).
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
                
            logger.info(f"LLM generated {len(actions)} RAG search intents.")
            return self._execute_rag_actions(actions)
            
        except Exception as e:
            logger.error(f"Error processing user request with LLM/RAG: {e}")
            return []

    def _execute_rag_actions(self, actions) -> list[RequestGroup]:
        final_groups = []
        for action in actions:
            logger.info(f"Executing RAG ({action.action_type}): '{action.search_query}'")
            extracted_tracks = []
            
            try:
                if action.action_type == 'track':
                    songs = self.yt.search(action.search_query, filter="songs", limit=5)
                    for s in songs:
                        title = s.get('title', '')
                        artists = [a['name'] for a in s.get('artists', []) if 'name' in a]
                        artist = ", ".join(artists) if artists else 'Unknown'
                        if title and artist:
                            extracted_tracks.append((title, artist))
                            break # Pick most relevant result
                            
                elif action.action_type == 'artist_hits':
                    songs = self.yt.search(action.search_query, filter="songs", limit=action.limit)
                    for s in songs:
                        title = s.get('title', '')
                        artists = [a['name'] for a in s.get('artists', []) if 'name' in a]
                        artist = ", ".join(artists) if artists else (s.get('artists', [{'name': ''}])[0].get('name', '') if s.get('artists') else 'Unknown')
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
                        logger.warning("Album not found, performing fallback song search...")
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
                                logger.error(f"Error extracting tracks from playlist {play_id}: {e}")
            except Exception as e:
                logger.error(f"Error in ytmusicapi during RAG: {e}")
                
            if extracted_tracks:
                logger.info(f"RAG extracted {len(extracted_tracks)} tracks from YouTube Music.")
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
                                reason=f"Extracted via YT Music ({action.action_type})"
                            )
                        )
                final_groups.append(RequestGroup(folder_name=action.folder_name, tracks=unique_tracks))
                
        return final_groups

    def generate_local_radio(self, vibra: str) -> None:
        if not self.client:
            return
            
        logger.info(f"Generating Local Radio for vibe: '{vibra}'")
        
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, artist, title, file_path FROM tracks WHERE status IN ('CINTA', 'PERMANENT')")
            all_tracks = cursor.fetchall()
            
        if not all_tracks:
            return
            
        prompt = f"""
        Act as a DJ. The user wants a local radio playlist matching this vibe: '{vibra}'.
        Here are the tracks available on their device.
        Pick the 40 tracks that BEST match this vibe.
        Return ONLY a JSON list of IDs.
        
        TRACKS:
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
            os.makedirs(self.paths.playlists_dir, exist_ok=True)
            m3u8_path = os.path.join(self.paths.playlists_dir, f"Radio_{self.sanitize_filename(vibra)}.m3u8")
            
            with open(m3u8_path, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
                for t_id in selected_ids:
                    f_path = next((t[3] for t in all_tracks if t[0] == t_id), None)
                    if f_path and os.path.exists(f_path):
                        rel_path = os.path.relpath(f_path, self.paths.playlists_dir)
                        f.write(f"{rel_path}\n")
                        
            logger.info(f"Local radio generated: {m3u8_path} with {len(selected_ids)} tracks.")
            
        except Exception as e:
            logger.error(f"Error generating local radio: {e}")

    def run_curation_cycle(self, slots: int) -> int:
        """Main curation loop that iterates until slots are filled or max attempts reached."""
        total_validated = 0
        
        batch_size = 50
        max_attempts = int(slots / batch_size) + 5
        attempts = 0
        
        while total_validated < slots and attempts < max_attempts:
            needed = slots - total_validated
            logger.info(f"Requesting {needed} recommendations from LLM (Attempt {attempts+1}/{max_attempts})")
            
            candidates = self.generate_recommendations(needed)
            if not candidates:
                attempts += 1
                import time
                time.sleep(15) # Avoid hammering API if rate limited
                continue
                
            validated = self.validate_and_save(candidates)
            total_validated += validated
            attempts += 1
            
        return total_validated
