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
    genre TEXT,
    track_number INTEGER,
    release_date TEXT
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

CREATE TABLE IF NOT EXISTS artist_genres (
    artist TEXT PRIMARY KEY,
    genre TEXT NOT NULL,
    source TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- High-performance indices to accelerate frequent queries
CREATE INDEX IF NOT EXISTS idx_tracks_status ON tracks(status);
CREATE INDEX IF NOT EXISTS idx_tracks_status_perm ON tracks(status, is_permanent);
CREATE INDEX IF NOT EXISTS idx_tracks_file_path ON tracks(file_path);
CREATE INDEX IF NOT EXISTS idx_tracks_artist_title ON tracks(artist, title);
CREATE INDEX IF NOT EXISTS idx_tracks_play_count ON tracks(play_count);

CREATE INDEX IF NOT EXISTS idx_listen_events_track_id ON listen_events(track_id);
CREATE INDEX IF NOT EXISTS idx_listen_events_listened_at ON listen_events(listened_at);

CREATE TABLE IF NOT EXISTS msid_cache (
    msid TEXT PRIMARY KEY,
    artist TEXT NOT NULL,
    title TEXT NOT NULL,
    resolved_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_msid_cache ON msid_cache(msid);

