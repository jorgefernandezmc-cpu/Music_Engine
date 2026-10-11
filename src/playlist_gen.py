import os
import sqlite3

class PlaylistGenerator:
    def __init__(self, db_path: str, storage_base: str = "storage"):
        self.db_path = db_path
        self.storage_base = storage_base
        self.playlists_dir = os.path.join(storage_base, "Playlists")
        os.makedirs(self.playlists_dir, exist_ok=True)
        
    def generate_descubrimiento_prioritario(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT file_path FROM tracks
                WHERE status = 'CINTA' AND play_count = 0
                ORDER BY added_at ASC
            """)
            tracks = cursor.fetchall()
            
        m3u8_path = os.path.join(self.playlists_dir, "Descubrimiento_Prioritario.m3u8")
        with open(m3u8_path, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            for t in tracks:
                rel_path = os.path.relpath(t[0], self.playlists_dir)
                f.write(f"{rel_path}\n")

    def generate_permanent_playlists(self):
        permanente_dir = os.path.join(self.storage_base, "Permanente")
        if not os.path.exists(permanente_dir):
            return
            
        for d in os.listdir(permanente_dir):
            dir_path = os.path.join(permanente_dir, d)
            if os.path.isdir(dir_path):
                m3u8_path = os.path.join(self.playlists_dir, f"{d}.m3u8")
                with open(m3u8_path, 'w', encoding='utf-8') as f:
                    f.write("#EXTM3U\n")
                    for file in sorted(os.listdir(dir_path)):
                        if file.endswith(('.opus', '.m4a', '.mp3')):
                            rel_path = os.path.relpath(os.path.join(dir_path, file), self.playlists_dir)
                            f.write(f"{rel_path}\n")
                            
    def generate_antojos_playlists(self):
        antojos_dir = os.path.join(self.storage_base, "Antojos")
        if not os.path.exists(antojos_dir):
            return
            
        for d in os.listdir(antojos_dir):
            dir_path = os.path.join(antojos_dir, d)
            if os.path.isdir(dir_path):
                m3u8_path = os.path.join(self.playlists_dir, f"Antojo_{d}.m3u8")
                with open(m3u8_path, 'w', encoding='utf-8') as f:
                    f.write("#EXTM3U\n")
                    for file in sorted(os.listdir(dir_path)):
                        if file.endswith(('.opus', '.m4a', '.mp3')):
                            rel_path = os.path.relpath(os.path.join(dir_path, file), self.playlists_dir)
                            f.write(f"{rel_path}\n")


    def generate_rotacion_viva(self):
        playlist_path = os.path.join(self.storage_base, "Playlists", "Rotación_Viva.m3u8")
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 1. Top 20 tracks (most played)
            cursor.execute('''
                SELECT t.id, t.file_path, t.genre
                FROM tracks t
                JOIN listen_events e ON t.id = e.track_id
                GROUP BY t.id
                ORDER BY COUNT(e.id) DESC
                LIMIT 20
            ''')
            top_20 = cursor.fetchall()
            
            if not top_20:
                return
                
            top_ids = [t[0] for t in top_20]
            top_paths = [t[1] for t in top_20]
            
            # Calculate genre distribution
            genre_counts = {}
            for t in top_20:
                g = t[2] or "Unknown"
                genre_counts[g] = genre_counts.get(g, 0) + 1
                
            # 2. Descubrimientos (5 tracks matching genre proportion)
            descubrimientos_paths = []
            top_20_len = len(top_20)
            
            for g, count in genre_counts.items():
                limit = round((count / top_20_len) * 5)
                if limit > 0:
                    cursor.execute(f'''
                        SELECT file_path FROM tracks 
                        WHERE genre = ? AND status IN ('PENDING', 'CINTA', 'ANTOJO') 
                        AND id NOT IN ({','.join(['?']*len(top_ids))})
                        ORDER BY RANDOM() LIMIT ?
                    ''', [g] + top_ids + [limit])
                    descubrimientos_paths.extend([r[0] for r in cursor.fetchall()])
            
            # 3. Olvidadas (5 tracks > 30 days without play)
            cursor.execute(f'''
                SELECT file_path FROM tracks 
                WHERE status = 'PERMANENT' 
                AND id NOT IN ({','.join(['?']*len(top_ids))})
                AND id NOT IN (
                    SELECT track_id FROM listen_events 
                    WHERE listened_at > datetime('now', '-30 days')
                )
                ORDER BY RANDOM() LIMIT 5
            ''', top_ids)
            olvidadas_paths = [r[0] for r in cursor.fetchall()]
            
            # Fallback if < 5 olvidadas
            if len(olvidadas_paths) < 5:
                needed = 5 - len(olvidadas_paths)
                exclude_paths = top_paths + descubrimientos_paths + olvidadas_paths
                exclude_placeholders = ','.join(['?'] * len(exclude_paths))
                
                cursor.execute(f'''
                    SELECT t.file_path 
                    FROM tracks t
                    LEFT JOIN listen_events e ON t.id = e.track_id
                    WHERE t.status = 'PERMANENT' 
                    AND t.file_path NOT IN ({exclude_placeholders})
                    GROUP BY t.id
                    ORDER BY COUNT(e.id) ASC
                    LIMIT ?
                ''', exclude_paths + [needed])
                olvidadas_paths.extend([r[0] for r in cursor.fetchall()])
                
            all_paths = top_paths + descubrimientos_paths + olvidadas_paths
            
            # Write M3U8
            with open(playlist_path, 'w', encoding='utf-8') as f:
                for path in all_paths:
                    if path:
                        # M3U8 paths are relative to Playlists folder
                        rel_path = path.replace('storage/', '../')
                        f.write(f"{rel_path}\n")
                        
        print(f"Rotación Viva generada: {len(all_paths)} pistas.")

    def update_all_playlists(self):
        self.generate_descubrimiento_prioritario()
        self.generate_permanent_playlists()
        self.generate_antojos_playlists()
        self.generate_rotacion_viva()
