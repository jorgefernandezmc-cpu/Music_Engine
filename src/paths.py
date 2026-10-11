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

class StoragePaths:
    """
    Centralizes and resolves all system storage paths
    from the configuration file (config/config.yaml).
    Allows changing directories without needing symbolic links.
    """
    def __init__(self, config_or_path="config/config.yaml"):
        if isinstance(config_or_path, dict):
            self.config = config_or_path
        else:
            if os.path.exists(config_or_path):
                with open(config_or_path, 'r', encoding='utf-8') as f:
                    self.config = yaml.safe_load(f) or {}
            else:
                self.config = {}

        storage_cfg = self.config.get('storage', {})
        
        # Base storage path
        base = storage_cfg.get('base_dir', '~/Music')
        self.base_dir = os.path.abspath(os.path.expanduser(base))
        
        # Main subdirectories
        cinta = storage_cfg.get('cinta_dir', storage_cfg.get('conveyor_dir', 'Cinta'))
        permanente = storage_cfg.get('permanente_dir', storage_cfg.get('permanent_dir', 'Permanente'))
        playlists = storage_cfg.get('playlists_dir', 'Playlists')
        peticiones_file = storage_cfg.get('peticiones_file', storage_cfg.get('requests_file', storage_cfg.get('antojos_file', 'peticiones.txt')))
        
        self.cinta_dir = os.path.join(self.base_dir, cinta)
        self.conveyor_dir = self.cinta_dir
        self.permanente_dir = os.path.join(self.base_dir, permanente)
        self.permanent_dir = self.permanente_dir
        self.playlists_dir = os.path.join(self.base_dir, playlists)
        
        # Requests mailbox file
        cand_peticiones = os.path.join(self.base_dir, 'peticiones.txt')
        cand_configured = os.path.join(self.base_dir, peticiones_file)
        if os.path.exists(cand_peticiones):
            self.peticiones_file = cand_peticiones
        else:
            self.peticiones_file = cand_configured
        self.requests_file = self.peticiones_file
            
    @property
    def antojos_file(self) -> str:
        # Backward compatibility
        return self.peticiones_file

    def ensure_dirs(self):
        """Ensures main directories exist on disk."""
        for d in [self.base_dir, self.cinta_dir, self.permanente_dir, self.playlists_dir]:
            os.makedirs(d, exist_ok=True)
        if not os.path.exists(self.peticiones_file):
            try:
                open(self.peticiones_file, 'a').close()
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
