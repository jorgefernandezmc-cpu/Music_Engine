import os
import re
import yaml

def sanitize_filename(name: str) -> str:
    """Sanitizes file or folder names to avoid forbidden filesystem characters."""
    if not name:
        return "Unknown"
    # Replace characters not allowed in file systems
    name = re.sub(r'[/\\:*?"<>|]', '-', str(name))
    # Clean leading and trailing dots and spaces
    name = name.strip('. ')
    return name or "Unknown"

DEFAULT_REQUESTS_HEADER = """# ==============================================================================
#                      REMOTE REQUESTS AND COMMANDS MAILBOX
# ==============================================================================
# Write your requests or commands at the bottom of this file (one per line).
# This header is always retained; only completed orders will be cleared.
# If any order cannot be completed, the reason will be reported right here.
#
# 1. REQUEST SONGS (PERMANENT OR TEMPORARY CRAVING):
#    - Permanent:  Download "Song Title" by Artist  OR  permanent: Artist - Song
#    - Craving:    craving: Artist - Song  OR  antojo: Artist - Song
#    - Discovery:  Duki / Melodic techno for workouts (AI catalog -> Permanent)
#
# 2. DOWNLOAD FULL ALBUMS (Official full album catalog):
#    - Permanent album: album: Artist - Album  OR  permanent album: Artist - Album
#    - Craving album:   craving album: Artist - Album  OR  antojo album: Artist - Album
#
# 3. REASSIGN SONG TO OFFICIAL ALBUM (Moves physical files and tags):
#    album: <Song> -> <Album Name>
#    Example:  album: NO PIENSO LLAMAR -> STORM
#
# 4. FIX OR ASSIGN MUSIC GENRE (SQLite + Physical metadata):
#    genre: <Song> -> <New Genre>
#    Example:  genre: So Payaso -> Hard Rock / Rock
#    (Or leave without arrow to auto-correct:  genre: Neverita)
#
# 5. UPDATE OR UPGRADE LYRICS (Fresh real-time synced .lrc download):
#    lyrics: <Song>
#    Example:  lyrics: Bohemian Rhapsody
#
# 6. SHIELD / PROMOTE SONG TO PERMANENT (Moves from Conveyor or Cravings to Permanent):
#    favorite: <Song>  OR  permanente: <Song>
#    Example:  favorite: Cuica
#
# 7. REMOVE / PURGE SONG (Physical deletion from Conveyor or Cravings):
#    purge: <Song>
#    Example:  purge: Song I Dislike
#
# 8. REPAIR QUESTIONABLE TRACK / AUDIT OFFICIAL VERSION:
#    fix: <Song Name>
#    Example:  fix: Me Enamoraste
#
# 9. CREATE INSTANT LOCAL RADIO (from your offline collection):
#    radio: <Vibe or Mood>
#    Example:  radio: Acoustic chill
# ==============================================================================
# WRITE YOUR REQUESTS BELOW:
"""

DEFAULT_PETICIONES_HEADER = DEFAULT_REQUESTS_HEADER

class StoragePaths:
    """
    Centralizes and resolves all system storage paths
    from the configuration file (config/config.yaml).
    Allows changing directories without needing symbolic links.
    """
    def __init__(self, config_or_path="config/config.yaml"):
        if isinstance(config_or_path, dict):
            self.config = config_or_path
            self.config_path = "config/config.yaml"
        else:
            self.config_path = str(config_or_path)
            if os.path.exists(config_or_path):
                with open(config_or_path, 'r', encoding='utf-8') as f:
                    self.config = yaml.safe_load(f) or {}
            else:
                self.config = {}

        storage_cfg = self.config.get('storage', {})
        
        # Base storage path
        base = storage_cfg.get('base_dir', '~/Music')
        self.base_dir = os.path.abspath(os.path.expanduser(base))
        
        # Main subdirectories (English defaults with transparent backward compatibility)
        conveyor = storage_cfg.get('conveyor_dir', storage_cfg.get('cinta_dir', 'Conveyor'))
        permanent = storage_cfg.get('permanent_dir', storage_cfg.get('permanente_dir', 'Permanent'))
        cravings = storage_cfg.get('cravings_dir', storage_cfg.get('antojos_dir', 'Cravings'))
        playlists = storage_cfg.get('playlists_dir', 'Playlists')
        requests_file = storage_cfg.get('requests_file', storage_cfg.get('peticiones_file', storage_cfg.get('antojos_file', 'requests.txt')))
        
        self.conveyor_dir = os.path.join(self.base_dir, conveyor)
        self.cinta_dir = self.conveyor_dir
        self.permanent_dir = os.path.join(self.base_dir, permanent)
        self.permanente_dir = self.permanent_dir
        self.cravings_dir = os.path.join(self.base_dir, cravings)
        self.antojos_dir = self.cravings_dir
        self.playlists_dir = os.path.join(self.base_dir, playlists)
        
        # Requests mailbox file (English default: requests.txt, with fallback to peticiones.txt if present)
        cand_configured = os.path.join(self.base_dir, requests_file)
        cand_peticiones = os.path.join(self.base_dir, 'peticiones.txt')
        cand_requests = os.path.join(self.base_dir, 'requests.txt')
        
        if os.path.exists(cand_configured):
            self.requests_file = cand_configured
        elif os.path.exists(cand_peticiones):
            self.requests_file = cand_peticiones
        elif os.path.exists(cand_requests):
            self.requests_file = cand_requests
        else:
            self.requests_file = cand_configured
            
        self.peticiones_file = self.requests_file
            
    @property
    def antojos_file(self) -> str:
        # Backward compatibility
        return self.peticiones_file

    def ensure_dirs(self):
        """Ensures main directories exist and initializes default requests mailbox if missing."""
        for d in [self.base_dir, self.cinta_dir, self.permanente_dir, self.cravings_dir, self.playlists_dir]:
            os.makedirs(d, exist_ok=True)
        if not os.path.exists(self.requests_file) or os.path.getsize(self.requests_file) == 0:
            try:
                with open(self.requests_file, 'w', encoding='utf-8') as f:
                    f.write(DEFAULT_REQUESTS_HEADER)
            except Exception:
                try:
                    open(self.requests_file, 'a').close()
                except Exception:
                    pass

    def get_permanente_track_path(self, artist: str, album: str, title: str, ext: str = "opus") -> str:
        """
        Returns absolute path in Permanent under hierarchy:
        Permanent/<Artist>/<Album>/<Artist> - <Title>.<ext>
        Without intermediate discovery or favorites subdirectories.
        """
        safe_artist = sanitize_filename(artist)
        safe_album = sanitize_filename(album if album and album.strip() else "Singles")
        safe_title = sanitize_filename(title)
        
        target_dir = os.path.join(self.permanente_dir, safe_artist, safe_album)
        filename = f"{safe_artist} - {safe_title}.{ext.lstrip('.')}"
        return os.path.join(target_dir, filename)

    get_permanent_track_path = get_permanente_track_path

    def get_cinta_track_path(self, artist: str, title: str, ext: str = "opus") -> str:
        """Returns path in Conveyor: Conveyor/<Artist> - <Title>.<ext>"""
        safe_artist = sanitize_filename(artist)
        safe_title = sanitize_filename(title)
        filename = f"{safe_artist} - {safe_title}.{ext.lstrip('.')}"
        return os.path.join(self.cinta_dir, filename)

    get_conveyor_track_path = get_cinta_track_path

    def get_craving_track_path(self, artist: str, album: str, title: str, ext: str = "opus") -> str:
        """
        Returns absolute path in Cravings under hierarchy:
        Cravings/<Artist>/<Album>/<Artist> - <Title>.<ext>
        """
        safe_artist = sanitize_filename(artist)
        safe_album = sanitize_filename(album if album and album.strip() else "Singles")
        safe_title = sanitize_filename(title)
        
        target_dir = os.path.join(self.cravings_dir, safe_artist, safe_album)
        filename = f"{safe_artist} - {safe_title}.{ext.lstrip('.')}"
        return os.path.join(target_dir, filename)

    get_antojo_track_path = get_craving_track_path
