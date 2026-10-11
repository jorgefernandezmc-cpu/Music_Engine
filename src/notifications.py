"""
notifications.py
Unified desktop notification system for Music Engine.
Sends native Linux notifications (Hyprland, Wayland, X11) asynchronously and non-blocking.
"""

import subprocess
import logging

logger = logging.getLogger('notifications')

def send_notification(title: str, message: str, urgency: str = "normal", enabled: bool = True):
    """
    Sends non-blocking desktop notifications on Linux (e.g. notify-send).
    If notify-send is unavailable or fails, logs debug information without halting execution.
    """
    if not enabled:
        return

    try:
        subprocess.Popen(
            ["notify-send", "-a", "Music Engine", "-u", urgency, "-i", "audio-headphones", title, message],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        logger.debug(f"Could not send desktop notification ({title}): {e}")
