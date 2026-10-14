"""
db.py
Centralized and optimized SQLite connection management with WAL mode and index creation.
"""

import sqlite3
import os
import logging

logger = logging.getLogger('db')

def get_db_connection(db_path: str = "data/conveyor_state.sqlite") -> sqlite3.Connection:
    """
    Returns an SQLite connection optimized for high performance:
    - WAL Mode (Write-Ahead Logging): Non-blocking concurrent reads and writes.
    - synchronous = NORMAL: Reduces disk I/O operations while maintaining durability.
    - foreign_keys = ON: Enforces referential integrity.
    - cache_size = -64000: Allocates up to 64MB of in-memory RAM cache.
    - temp_store = MEMORY: Stores temporary tables in RAM.
    """
    os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA cache_size = -64000;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    return conn


def ensure_db_indexes(conn: sqlite3.Connection) -> None:
    """
    Ensures critical indices exist to accelerate bulk filtering queries
    (status, file_path, artist/title, listen_events, etc.).
    """
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS artist_genres (
            artist TEXT PRIMARY KEY,
            genre TEXT NOT NULL,
            source TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS msid_cache (
            msid TEXT PRIMARY KEY,
            artist TEXT NOT NULL,
            title TEXT NOT NULL,
            resolved_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_msid_cache ON msid_cache(msid);")
    
    # Indices on tracks
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracks_status ON tracks(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracks_status_perm ON tracks(status, is_permanent);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracks_file_path ON tracks(file_path);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracks_artist_title ON tracks(artist, title);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracks_play_count ON tracks(play_count);")
    
    # Indices on listen_events
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_listen_events_track_id ON listen_events(track_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_listen_events_listened_at ON listen_events(listened_at);")
    
    conn.commit()
