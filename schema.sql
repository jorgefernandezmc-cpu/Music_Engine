CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    album TEXT,
    duration_seconds INTEGER,
    status TEXT NOT NULL,
    is_permanent BOOLEAN DEFAULT 0,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_played_at DATETIME,
    play_count INTEGER DEFAULT 0,
    skip_count INTEGER DEFAULT 0,
    file_path TEXT,
    genre TEXT
);
CREATE TABLE IF NOT EXISTS listen_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id TEXT NOT NULL,
    listened_at DATETIME NOT NULL,
    source TEXT,
    FOREIGN KEY(track_id) REFERENCES tracks(id)
);
CREATE TABLE IF NOT EXISTS system_metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS orphan_scrobbles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artist TEXT,
    title TEXT,
    attempts INTEGER DEFAULT 0,
    UNIQUE(artist, title)
);
