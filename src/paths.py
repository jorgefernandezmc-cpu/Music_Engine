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

DEFAULT_REQUESTS_HEADER_EN = """# ==============================================================================
#                      REMOTE REQUESTS AND COMMANDS MAILBOX
# ==============================================================================
# Write your requests or commands at the bottom of this file (one per line).
# This header is always retained; only completed orders will be cleared.
# If any order cannot be completed, the reason will be reported right here.
#
# 1. REQUEST SONGS (PERMANENT OR TEMPORARY CRAVING):
#    - Permanent:  Download "Song Title" by Artist  OR  permanent: Artist - Song
#    - Craving:    craving: Artist - Song  OR  antojo: Artist - Song
#    - Direct URL: https://music.youtube.com/watch?v=...  (or craving: https://...)
#    - Discovery:  Duki / Melodic techno for workouts (AI catalog -> Permanent)
#
# 2. DOWNLOAD FULL ALBUMS (Official full album catalog):
#    - Permanent album: album: Artist - Album  OR  permanent album: Artist - Album
#    - Craving album:   craving album: Artist - Album  OR  antojo album: Artist - Album
#
# 3. REPAIR OR REPLACE AUDIO (Auto studio search OR manual YT Music URL):
#    - Auto-fix:   fix: Artist - Song
#    - Manual URL: fix: Artist - Song -> https://music.youtube.com/watch?v=...
#
# 4. REASSIGN ALBUM OR ARTIST (Moves physical files and updates tags):
#    - Album:      album: <Song> -> <Album Name>
#    - Artist:     artist: <Song> -> <New Artist>
#
# 5. PERSONAL PLAYLISTS (Add/Remove from user playlists):
#    - Add:        playlist: Workout += Eye of the Tiger
#    - Remove:     playlist: Workout -= Eye of the Tiger
#
# 6. FORCE RE-DOWNLOAD TRACK (Cleans cache and re-downloads fresh):
#    redownload: <Artist - Song>
#
# 7. INSPECT TRACK INFORMATION:
#    info: <Artist - Song>
#
# 8. UPDATE OR UPGRADE LYRICS (Fresh real-time synced .lrc download):
#    lyrics: <Song>
#
# 9. FIX OR ASSIGN MUSIC GENRE (SQLite + Physical metadata):
#    genre: <Song> -> <New Genre>  (or leave without arrow to auto-detect)
#
# 10. SHIELD / PROMOTE SONG TO PERMANENT (Moves from Conveyor or Cravings):
#    favorite: <Song>  OR  shield: <Song>  OR  permanente: <Song>
#
# 11. REMOVE / PURGE SONGS:
#    - From Conveyor/Cravings:  purge: <Song>  OR  delete: <Song>
#    - From Permanent Library:  purge permanent: <Artist - Song>
#
# 12. CREATE INSTANT LOCAL RADIO (from your offline collection):
#    radio: <Vibe or Mood>
# ==============================================================================
# WRITE YOUR REQUESTS BELOW:
"""

DEFAULT_REQUESTS_HEADER_ES = """# ==============================================================================
#                    BUZÓN REMOTO DE PETICIONES Y COMANDOS
# ==============================================================================
# Escribe tus peticiones o comandos al final de este archivo (uno por línea).
# Esta cabecera siempre se conserva; solo se borrarán las órdenes completadas.
# Si alguna orden no puede completarse, se indicará el motivo aquí mismo.
#
# 1. PEDIR CANCIONES (PERMANENTE O ANTOJO TEMPORAL):
#    - Permanente:  Descargar "Título" de Artista  O  permanente: Artista - Tema
#    - Antojo:      antojo: Artista - Tema  O  craving: Artista - Tema
#    - Enlace URL:  https://music.youtube.com/watch?v=...  (o antojo: https://...)
#    - Descubrir:   Duki / Melodic techno para entrenar (Catálogo IA -> Permanente)
#
# 2. DESCARGAR DISCOS COMPLETOS (Catálogo oficial de álbumes completos):
#    - Álbum permanente: disco: Artista - Disco  O  album: Artista - Álbum
#    - Álbum en antojo:  antojo album: Artista - Disco  O  craving album: Artista - Álbum
#
# 3. REPARAR O CAMBIAR AUDIO (Búsqueda oficial de estudio O enlace manual de YT Music):
#    - Auto-reparar:  reparar: Artista - Tema  (o fix: Tema)
#    - Enlace manual: reparar: Artista - Tema -> https://music.youtube.com/watch?v=...
#
# 4. REASIGNAR ÁLBUM O ARTISTA (Mueve archivos físicos y actualiza etiquetas):
#    - Álbum:         album: <Tema> -> <Nombre del Álbum>
#    - Artista:       artista: <Tema> -> <Nuevo Artista>
#
# 5. LISTAS DE REPRODUCCIÓN PROPIAS (Añadir/Quitar temas):
#    - Añadir:        lista: Gym += Eye of the Tiger
#    - Quitar:        lista: Gym -= Eye of the Tiger
#
# 6. FORZAR RE-DESCARGA DE PISTA (Borra caché y descarga de nuevo limpia):
#    redescargar: <Artista - Tema>  (o redownload: Tema)
#
# 7. CONSULTAR INFORMACIÓN DE UNA PISTA:
#    info: <Artista - Tema>  (o informacion: Tema)
#
# 8. ACTUALIZAR LETRAS SINCRONIZADAS (Descarga en tiempo real de .lrc sincronizado):
#    letra: <Tema>  O  lyrics: <Tema>
#
# 9. CORREGIR O ASIGNAR GÉNERO (SQLite + Metadatos físicos):
#    genero: <Tema> -> <Nuevo Género>  (o sin flecha para auto-detectar con IA)
#
# 10. BLINDAR / PROMOVER TEMA A PERMANENTE (Mueve de Cinta o Antojos):
#    favorita: <Tema>  O  blindar: <Tema>  O  permanente: <Tema>
#
# 11. BORRAR / PURGAR CANCIONES:
#    - De Cinta o Antojos:      borrar: <Tema>  O  eliminar: <Tema>
#    - De Colección Permanente: borrar permanente: <Artista - Tema>
#
# 12. GENERAR RADIO LOCAL INSTANTÁNEA (de tu colección sin conexión):
#    radio: <Ambiente o Estilo>
# ==============================================================================
# ESCRIBE TUS PETICIONES DEBAJO:
"""

DEFAULT_REQUESTS_HEADER = DEFAULT_REQUESTS_HEADER_EN
DEFAULT_PETICIONES_HEADER = DEFAULT_REQUESTS_HEADER_ES


def get_mailbox_header(language: str = "en") -> str:
    """Returns the mailbox header template for the requested language ('en' or 'es')."""
    lang = (language or "en").strip().lower()
    if lang == "es":
        return DEFAULT_REQUESTS_HEADER_ES
    return DEFAULT_REQUESTS_HEADER_EN


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
        
        # System language ("en" or "es", default: "en")
        self.language = str(self.config.get('system', {}).get('language', 'en')).strip().lower()
        if self.language not in ['en', 'es']:
            self.language = 'en'
            
    @property
    def antojos_file(self) -> str:
        # Backward compatibility
        return self.peticiones_file

    @property
    def lune_backup_file(self) -> str:
        """Returns the configured Lune backup JSON filename."""
        return self.config.get('playlists', {}).get('lune_backup_file', 'lune_playlists_backup.json')

    @property
    def lune_backup_path(self) -> str:
        """Returns the absolute path to the Lune backup JSON file."""
        return os.path.join(self.playlists_dir, self.lune_backup_file)

    @property
    def user_playlists_dir_name(self) -> str:
        """Returns the configured folder name for user-created Lune playlists."""
        return self.config.get('playlists', {}).get('user_playlists_dir', 'Listas Propias')

    @property
    def user_playlists_dir(self) -> str:
        """Returns the absolute path to the folder containing user-created Lune playlists."""
        return os.path.join(self.playlists_dir, self.user_playlists_dir_name)

    @property
    def backup_dir(self) -> str:
        """Returns the configured absolute backup directory."""
        configured = self.config.get('backup', {}).get('dir', self.config.get('storage', {}).get('backup_dir', 'data/backups'))
        return os.path.abspath(os.path.expanduser(configured))

    def sync_mailbox_header(self):
        """
        Ensures the mailbox file exists and has the guide header in the configured language.
        If the user changed system.language in config.yaml, updates the header
        without removing or modifying any user requests, commands, or error notes.
        """
        target_header = get_mailbox_header(self.language)
        if not os.path.exists(self.requests_file) or os.path.getsize(self.requests_file) == 0:
            try:
                with open(self.requests_file, 'w', encoding='utf-8') as f:
                    f.write(target_header)
            except Exception:
                try:
                    open(self.requests_file, 'a').close()
                except Exception:
                    pass
            return

        try:
            with open(self.requests_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            return

        # Check if the file contains one of our recognized tutorial headers
        is_en_header = "REMOTE REQUESTS AND COMMANDS MAILBOX" in content
        is_es_header = "BUZÓN REMOTO DE PETICIONES Y COMANDOS" in content

        # If it doesn't have either header, it is a custom user file, leave untouched
        if not is_en_header and not is_es_header:
            return

        # Check if header already matches target language
        target_is_es = (self.language == "es")
        if target_is_es and is_es_header and not is_en_header:
            return
        if not target_is_es and is_en_header and not is_es_header:
            return

        # Separate header lines from user commands
        lines = content.splitlines(keepends=True)
        user_lines = []
        in_header = True

        for line in lines:
            s_line = line.strip()
            if in_header:
                if (s_line.startswith("# WRITE YOUR REQUESTS BELOW:") or
                    s_line.startswith("# ESCRIBE TUS PETICIONES DEBAJO:")):
                    in_header = False
                elif not s_line.startswith("#") and s_line != "":
                    in_header = False
                    user_lines.append(line)
            else:
                user_lines.append(line)

        # Reconstruct with target header and preserved user commands
        new_content = target_header
        if user_lines:
            if not new_content.endswith("\n"):
                new_content += "\n"
            while user_lines and user_lines[0].strip() == "":
                user_lines.pop(0)
            new_content += "".join(user_lines)

        try:
            with open(self.requests_file, 'w', encoding='utf-8') as f:
                f.write(new_content)
        except Exception:
            pass

    def ensure_dirs(self):
        """Ensures main directories exist and initializes or syncs requests mailbox."""
        for d in [self.base_dir, self.cinta_dir, self.permanente_dir, self.cravings_dir, self.playlists_dir, self.user_playlists_dir, self.backup_dir]:
            os.makedirs(d, exist_ok=True)
        self.sync_mailbox_header()

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
