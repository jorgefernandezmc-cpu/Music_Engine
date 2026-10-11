import os
import sqlite3
import urllib.parse
import urllib.request
import json
import time
import logging
from mutagen.oggopus import OggOpus

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('lyric_enricher')

def enrich_legacy_lyrics(db_path="data/conveyor_state.sqlite"):
    logger.info("Iniciando escaneo de letras en segundo plano...")
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, artist, file_path FROM tracks WHERE file_path IS NOT NULL AND status != 'FAILED'")
        tracks = cursor.fetchall()
        
    enriched = 0
    skipped = 0
    not_found = 0
    
    for t_id, title, artist, f_path in tracks:
        if not f_path or not os.path.exists(f_path):
            continue
            
        if not f_path.endswith('.opus'):
            continue
            
        try:
            audio = OggOpus(f_path)
            if "LYRICS" in audio:
                skipped += 1
                continue
                
            logger.info(f"Buscando letra para: {artist} - {title}")
            query = urllib.parse.urlencode({'track_name': title, 'artist_name': artist})
            req = urllib.request.Request(f"https://lrclib.net/api/search?{query}", headers={'User-Agent': 'MusicConveyorBot/1.0'})
            
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                if data and len(data) > 0:
                    synced = data[0].get('syncedLyrics')
                    plain = data[0].get('plainLyrics')
                    best_lyrics = synced if synced else plain
                    
                    if best_lyrics:
                        audio["LYRICS"] = best_lyrics
                        audio.save()
                        enriched += 1
                        logger.info(f"Letra incrustada ({enriched})")
                    else:
                        not_found += 1
                else:
                    not_found += 1
                    
        except urllib.error.HTTPError as e:
            if e.code == 429:
                logger.warning("Rate limit alcanzado, pausando 10s...")
                time.sleep(10)
            else:
                logger.error(f"Error HTTP {e.code} en {title}")
        except Exception as e:
            logger.error(f"Error procesando {title}: {e}")
            
        time.sleep(1.0)
        
    logger.info(f"Escaneo finalizado. Incrustadas: {enriched}, Omitidas (ya tenían): {skipped}, No encontradas: {not_found}")

if __name__ == "__main__":
    enrich_legacy_lyrics()
