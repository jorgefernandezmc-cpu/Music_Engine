"""
notifications.py
Unified desktop notification system for Music Engine.
Sends native Linux notifications (Hyprland, Wayland, X11) asynchronously and non-blocking.
Supports bilingual output (English / Spanish) based on system configuration.
"""

import subprocess
import logging
import re

logger = logging.getLogger('notifications')

# Global default language
_CURRENT_LANGUAGE = "en"

TITLE_TRANSLATIONS_ES = {
    "Album Updated": "Álbum Actualizado",
    "Genre Updated": "Género Actualizado",
    "Lyrics Updated": "Letras Actualizadas",
    "Shielded in Permanent": "Blindada en Permanente",
    "Track Purged": "Pista Purgada",
    "Permanent Track Purged": "Pista Permanente Purgada",
    "Artist Updated": "Artista Actualizado",
    "Redownload Queued": "Re-descarga Encolada",
    "Playlist Updated": "Lista Actualizada",
    "URL Queued": "Enlace Encolado",
    "Album Queued": "Álbum Encolado",
    "Track Queued": "Pista Encolada",
    "Track Repaired": "Pista Reparada",
    "Local Radio Generated": "Radio Local Generada",
}

BODY_REPLACEMENTS_ES = [
    (r"⏱ Total time:\s*", "⏱ Tiempo total: "),
    (r"(\d+)\s+new songs downloaded", r"\1 nuevas canciones descargadas"),
    (r"(\d+)\s+scrobbles synced", r"\1 scrobbles sincronizados"),
    (r"(\d+)\s+promoted to Permanent", r"\1 promocionadas a Permanente"),
    (r"(\d+)\s+tracks rotated/purged", r"\1 pistas rotadas/purgadas"),
    (r"📁 M3U8 playlists and library updated", "📁 Listas M3U8 y biblioteca actualizadas"),
    (r"Moved to:\s*", "Movida a: "),
    (r"Moved to Permanent/", "Movida a Permanent/"),
    (r"New genre:\s*", "Nuevo género: "),
    (r"New artist:\s*", "Nuevo artista: "),
    (r"Official version will be downloaded", "Se descargará la versión oficial"),
    (r"Audio will be re-downloaded", "El audio se volverá a descargar"),
    (r"Audio replaced from provided URL", "Audio reemplazado con el enlace facilitado"),
    (r"Added to playlist\s*", "Añadida a la lista "),
    (r"Removed from playlist\s*", "Eliminada de la lista "),
    (r"Removed from Permanent", "Eliminada de Permanente"),
    (r"Removed from\s*", "Eliminada de "),
    (r"(\d+)/(\d+)\s+tracks queued to\s*", r"\1/\2 pistas encoladas en "),
    (r"Queued to\s*", "Encolada en "),
    (r"Vibe:\s*", "Ambiente: "),
]


def set_notification_language(lang: str):
    """Sets the active language for desktop notifications ('en' or 'es')."""
    global _CURRENT_LANGUAGE
    l = (lang or "en").strip().lower()
    _CURRENT_LANGUAGE = "es" if l == "es" else "en"


def get_notification_language() -> str:
    """Returns the current notification language."""
    return _CURRENT_LANGUAGE


def _localize(text: str, is_title: bool = False, lang: str = "en") -> str:
    if lang != "es":
        return text

    if is_title:
        # Check exact match
        if text in TITLE_TRANSLATIONS_ES:
            return TITLE_TRANSLATIONS_ES[text]
        # Check dynamic title
        if text.startswith("🎵 Music Engine Synchronized"):
            return text.replace("🎵 Music Engine Synchronized", "🎵 Music Engine Sincronizado")
        return text

    # Body localization
    res = text
    for pattern, repl in BODY_REPLACEMENTS_ES:
        res = re.sub(pattern, repl, res)
    return res


def send_notification(title: str, message: str, urgency: str = "normal", enabled: bool = True, lang: str = None):
    """
    Sends non-blocking desktop notifications on Linux (e.g. notify-send).
    If notify-send is unavailable or fails, logs debug information without halting execution.
    Automatically localizes text if lang (or global language) is set to 'es'.
    """
    if not enabled:
        return

    active_lang = (lang or _CURRENT_LANGUAGE).strip().lower()
    final_title = _localize(title, is_title=True, lang=active_lang)
    final_message = _localize(message, is_title=False, lang=active_lang)

    try:
        subprocess.Popen(
            ["notify-send", "-a", "Music Engine", "-u", urgency, "-i", "audio-headphones", final_title, final_message],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        logger.debug(f"Could not send desktop notification ({title}): {e}")
