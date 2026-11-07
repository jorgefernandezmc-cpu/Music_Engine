"""
mpris_scrobbler.py
Lightweight, resilient Linux MPRIS scrobbler daemon with persistent local SQLite queue.

Features:
- Monitors media players via MPRIS D-Bus interface (e.g. WaveFlow, Spotify, browsers).
- Strict offline support: scrobbles are NEVER lost when offline.
- Persistent local SQLite queue (pending_scrobbles).
- Automatic batch sync with ListenBrainz (/1/submit-listens) when internet is available.
- Industry-standard qualification: 50% of song or 240 seconds (configurable).
- Zero heavy dependencies (uses jeepney for pure-Python D-Bus communication).
"""

import os
import sys
import time
import signal
import sqlite3
import logging
import requests
import re
import yaml
from datetime import datetime, timezone
from dotenv import load_dotenv

try:
    from jeepney import DBusAddress, new_method_call
    from jeepney.io.blocking import open_dbus_connection
except ImportError:
    print("[Error] 'jeepney' package is required. Install it with: pip install jeepney")
    sys.exit(1)


# Setup logger
os.makedirs("logs", exist_ok=True)
logger = logging.getLogger("scrobbler")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fh = logging.FileHandler("logs/scrobbler.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] [Scrobbler] %(message)s"))
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] [Scrobbler] %(message)s"))
    logger.addHandler(fh)
    logger.addHandler(sh)


class MprisScrobbler:
    def __init__(self, config_path: str = "config/config.yaml", db_path: str = None):
        self.config_path = config_path
        self.config = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {}

        # Load environment variables
        env_cand = os.path.join(os.path.dirname(config_path), ".env")
        if os.path.exists(env_cand):
            load_dotenv(env_cand)
        elif os.path.exists(".env"):
            load_dotenv(".env")

        scrobbler_cfg = self.config.get("scrobbler", {})
        self.min_play_time = int(scrobbler_cfg.get("min_play_time", 45))
        self.completion_ratio = float(scrobbler_cfg.get("completion_ratio", 0.50))
        self.whitelist = scrobbler_cfg.get("player_whitelist", ["waveflow"])
        if isinstance(self.whitelist, str):
            self.whitelist = [self.whitelist]

        # Queue SQLite Database
        queue_cand = db_path or scrobbler_cfg.get("queue_db", "data/scrobbler_queue.sqlite")
        self.queue_db = queue_cand
        os.makedirs(os.path.dirname(self.queue_db) or ".", exist_ok=True)
        self._init_queue_db()

        # ListenBrainz credentials
        self.lb_token = os.getenv("LISTENBRAINZ_TOKEN") or scrobbler_cfg.get("token")
        self.lb_user = os.getenv("LISTENBRAINZ_USER") or scrobbler_cfg.get("user")
        self.api_url = scrobbler_cfg.get("api_url", "https://api.listenbrainz.org/1").rstrip("/")

        # Playback tracking per player: player_bus -> state_dict
        self.tracked_players = {}
        self.running = True
        self.last_flush_check = 0
        self.flush_interval = 30  # seconds between queue flush attempts

        # D-Bus Connection
        self.bus_conn = None
        self._connect_dbus()

    def _init_queue_db(self):
        """Initializes the persistent SQLite queue table."""
        with sqlite3.connect(self.queue_db) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_scrobbles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artist TEXT NOT NULL,
                    title TEXT NOT NULL,
                    album TEXT,
                    duration_s INTEGER,
                    listened_at INTEGER NOT NULL,
                    player TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    retry_count INTEGER DEFAULT 0
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pending_created ON pending_scrobbles(created_at);")
            conn.commit()

    def _connect_dbus(self):
        """Connects to user session D-Bus."""
        try:
            self.bus_conn = open_dbus_connection(bus="SESSION")
            logger.info("Connected to Session D-Bus successfully.")
        except Exception as e:
            logger.error(f"Failed to connect to Session D-Bus: {e}")
            self.bus_conn = None

    def _matches_whitelist(self, player_bus: str) -> bool:
        """Checks if a player matches the configured whitelist (supports regex and substring)."""
        if not self.whitelist or "*" in self.whitelist:
            return True
        short_name = player_bus.replace("org.mpris.MediaPlayer2.", "")
        for pattern in self.whitelist:
            if re.search(pattern, short_name, re.IGNORECASE) or re.search(pattern, player_bus, re.IGNORECASE):
                return True
        return False

    def enqueue_scrobble(self, artist: str, title: str, album: str, duration_s: int, listened_at: int, player: str):
        """Inserts qualified scrobble into persistent SQLite queue."""
        if not artist or not title:
            return
        with sqlite3.connect(self.queue_db) as conn:
            conn.execute("""
                INSERT INTO pending_scrobbles (artist, title, album, duration_s, listened_at, player)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (artist, title, album or "", duration_s, listened_at, player))
            conn.commit()
        logger.info(f"💾 Scrobble saved in offline queue: '{artist} - {title}' (listened at {listened_at})")
        
        # Trigger immediate non-blocking flush attempt
        self.flush_queue()

    def flush_queue(self, limit: int = 50) -> tuple[bool, int]:
        """Flushes pending scrobbles to ListenBrainz API."""
        if not self.lb_token:
            logger.warning("No ListenBrainz token configured; scrobbles will remain queued in SQLite.")
            return False, 0

        with sqlite3.connect(self.queue_db) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, artist, title, album, duration_s, listened_at, player
                FROM pending_scrobbles
                ORDER BY id ASC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()

        if not rows:
            return True, 0

        listens_payload = []
        row_ids = []
        for r in rows:
            r_id, r_artist, r_title, r_album, r_dur, r_ts, r_player = r
            row_ids.append(r_id)
            meta = {
                "artist_name": r_artist,
                "track_name": r_title,
                "additional_info": {
                    "media_player": r_player or "MPRIS",
                    "submission_client": "MusicEngine_Scrobbler"
                }
            }
            if r_album:
                meta["release_name"] = r_album
            if r_dur and r_dur > 0:
                meta["additional_info"]["duration"] = r_dur

            listens_payload.append({
                "listened_at": int(r_ts),
                "track_metadata": meta
            })

        submit_url = f"{self.api_url}/submit-listens"
        headers = {
            "Authorization": f"Token {self.lb_token}",
            "Content-Type": "application/json"
        }
        body = {
            "listen_type": "import",
            "payload": listens_payload
        }

        try:
            resp = requests.post(submit_url, headers=headers, json=body, timeout=10)
            if resp.status_code == 200:
                with sqlite3.connect(self.queue_db) as conn:
                    ids_clause = ",".join("?" for _ in row_ids)
                    conn.execute(f"DELETE FROM pending_scrobbles WHERE id IN ({ids_clause})", tuple(row_ids))
                    conn.commit()
                logger.info(f"🚀 Successfully uploaded {len(row_ids)} scrobbles to ListenBrainz!")
                return True, len(row_ids)
            else:
                logger.warning(f"ListenBrainz rejected scrobble batch (status {resp.status_code}): {resp.text}")
                return False, 0
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            logger.debug(f"Device offline or network unreachable ({e}). Kept {len(row_ids)} scrobbles in queue.")
            with sqlite3.connect(self.queue_db) as conn:
                ids_clause = ",".join("?" for _ in row_ids)
                conn.execute(f"UPDATE pending_scrobbles SET retry_count = retry_count + 1 WHERE id IN ({ids_clause})", tuple(row_ids))
                conn.commit()
            return False, 0
        except Exception as e:
            logger.error(f"Unexpected error submitting scrobbles: {e}")
            return False, 0

    def send_now_playing(self, artist: str, title: str, album: str = None):
        """Sends 'playing_now' notification to ListenBrainz (best-effort, non-blocking)."""
        if not self.lb_token:
            return
        body = {
            "listen_type": "playing_now",
            "payload": [{
                "track_metadata": {
                    "artist_name": artist,
                    "track_name": title,
                    "release_name": album or "",
                    "additional_info": {
                        "submission_client": "MusicEngine_Scrobbler"
                    }
                }
            }]
        }
        try:
            requests.post(
                f"{self.api_url}/submit-listens",
                headers={"Authorization": f"Token {self.lb_token}", "Content-Type": "application/json"},
                json=body,
                timeout=3
            )
        except Exception:
            pass

    def get_pending_count(self) -> int:
        """Returns the number of currently pending offline scrobbles."""
        with sqlite3.connect(self.queue_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM pending_scrobbles")
            return cursor.fetchone()[0]

    def _query_mpris_players(self) -> list[str]:
        """Queries D-Bus for all available MPRIS media player services."""
        if not self.bus_conn:
            self._connect_dbus()
            if not self.bus_conn:
                return []
        try:
            bus_msg = new_method_call(
                DBusAddress("/org/freedesktop/DBus", bus_name="org.freedesktop.DBus", interface="org.freedesktop.DBus"),
                "ListNames"
            )
            reply = self.bus_conn.send_and_get_reply(bus_msg)
            names = reply.body[0]
            return [n for n in names if n.startswith("org.mpris.MediaPlayer2.")]
        except Exception as e:
            logger.debug(f"Error querying D-Bus player list: {e}")
            self.bus_conn = None
            return []

    def _get_player_properties(self, player_bus: str) -> dict:
        """Extracts status and metadata dictionary from a player."""
        if not self.bus_conn:
            return {}
        try:
            prop_msg = new_method_call(
                DBusAddress("/org/mpris/MediaPlayer2", bus_name=player_bus, interface="org.freedesktop.DBus.Properties"),
                "GetAll",
                "s",
                ("org.mpris.MediaPlayer2.Player",)
            )
            res = self.bus_conn.send_and_get_reply(prop_msg, timeout=2.0)
            props = res.body[0]
            status = props.get("PlaybackStatus", (None, "Stopped"))[1]

            sig, meta_dict = props.get("Metadata", (None, {}))
            title = meta_dict.get("xesam:title", (None, ""))[1]
            artist_raw = meta_dict.get("xesam:artist", (None, []))[1]
            if isinstance(artist_raw, list):
                artist = ", ".join(artist_raw)
            else:
                artist = str(artist_raw)

            album = meta_dict.get("xesam:album", (None, ""))[1]
            length_us = meta_dict.get("mpris:length", (None, 0))[1]
            duration_s = int(length_us // 1000000) if length_us else 0
            trackid = meta_dict.get("mpris:trackid", (None, ""))[1]

            return {
                "status": status,
                "title": title.strip(),
                "artist": artist.strip(),
                "album": album.strip(),
                "duration_s": duration_s,
                "trackid": trackid
            }
        except Exception:
            return {}

    def poll_cycle(self):
        """Performs one poll cycle across all matching MPRIS players."""
        now = time.time()
        active_players = self._query_mpris_players()

        # Check existing tracked players against active list
        dead_players = [p for p in self.tracked_players if p not in active_players]
        for dp in dead_players:
            prev = self.tracked_players.pop(dp, None)
            if prev and prev.get("qualified") and not prev.get("enqueued"):
                self.enqueue_scrobble(
                    prev["artist"], prev["title"], prev["album"],
                    prev["duration_s"], int(prev["start_ts"]), prev["player_name"]
                )

        # Inspect each active player
        for p_bus in active_players:
            if not self._matches_whitelist(p_bus):
                continue

            props = self._get_player_properties(p_bus)
            if not props or not props.get("title"):
                continue

            status = props["status"]
            title = props["title"]
            artist = props["artist"]
            album = props["album"]
            dur_s = props["duration_s"]
            short_player = p_bus.replace("org.mpris.MediaPlayer2.", "")

            state = self.tracked_players.get(p_bus)
            is_new_track = (not state) or (state["title"] != title or state["artist"] != artist)

            if is_new_track:
                # If old track qualified, queue it now
                if state and state.get("qualified") and not state.get("enqueued"):
                    self.enqueue_scrobble(
                        state["artist"], state["title"], state["album"],
                        state["duration_s"], int(state["start_ts"]), state["player_name"]
                    )

                self.tracked_players[p_bus] = {
                    "player_name": short_player,
                    "title": title,
                    "artist": artist,
                    "album": album,
                    "duration_s": dur_s,
                    "start_ts": now,
                    "last_tick": now,
                    "listened_s": 0.0,
                    "status": status,
                    "qualified": False,
                    "enqueued": False
                }
                if status == "Playing":
                    logger.info(f"▶️ Playing on {short_player}: {artist} - {title}")
                    self.send_now_playing(artist, title, album)
                continue

            # Update existing track progression
            dt = max(0.0, min(5.0, now - state["last_tick"]))
            state["last_tick"] = now

            if status == "Playing":
                state["listened_s"] += dt

                # Calculate qualification threshold
                # Rule: 50% duration (or 240s max), but at least min_play_time
                if dur_s > 0:
                    req_time = min(240, max(self.min_play_time, dur_s * self.completion_ratio))
                else:
                    req_time = self.min_play_time

                if not state["qualified"] and state["listened_s"] >= req_time:
                    state["qualified"] = True
                    state["enqueued"] = True
                    logger.info(f"✓ Track qualified ({int(state['listened_s'])}s/{req_time}s): {artist} - {title}")
                    self.enqueue_scrobble(
                        artist, title, album, dur_s,
                        int(state["start_ts"]), short_player
                    )

            state["status"] = status

        # Periodic queue flush (every 30 seconds)
        if now - self.last_flush_check >= self.flush_interval:
            self.last_flush_check = now
            pending = self.get_pending_count()
            if pending > 0:
                logger.debug(f"Periodic flush check: {pending} scrobbles in queue.")
                self.flush_queue()

    def run(self):
        """Main service loop."""
        logger.info("==================================================")
        logger.info(" MPRIS Scrobbler Daemon started with Offline Queue")
        logger.info(f" Whitelist: {self.whitelist}")
        logger.info(f" Min play time: {self.min_play_time}s | Completion: {int(self.completion_ratio*100)}%")
        logger.info(f" Queue database: {self.queue_db}")
        pending = self.get_pending_count()
        logger.info(f" Pending scrobbles in queue: {pending}")
        logger.info("==================================================")

        # Attempt initial flush if connected
        if pending > 0:
            self.flush_queue()

        def _handle_exit(sig, frame):
            logger.info("Shutdown signal received. Saving qualified tracks and exiting...")
            for p_bus, state in self.tracked_players.items():
                if state and state.get("qualified") and not state.get("enqueued"):
                    self.enqueue_scrobble(
                        state["artist"], state["title"], state["album"],
                        state["duration_s"], int(state["start_ts"]), state["player_name"]
                    )
            self.running = False

        signal.signal(signal.SIGINT, _handle_exit)
        signal.signal(signal.SIGTERM, _handle_exit)

        while self.running:
            try:
                self.poll_cycle()
            except Exception as e:
                logger.error(f"Error in scrobbler poll cycle: {e}")
            time.sleep(1.0)

        logger.info("MPRIS Scrobbler Daemon stopped cleanly.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MPRIS Scrobbler Daemon with Offline Queue")
    parser.add_argument("--config", default="config/config.yaml", help="Path to config.yaml")
    parser.add_argument("--status", action="store_true", help="Display pending offline scrobbles")
    parser.add_argument("--flush", action="store_true", help="Flush pending queue immediately")
    args = parser.parse_args()

    scrobbler = MprisScrobbler(config_path=args.config)
    if args.status:
        count = scrobbler.get_pending_count()
        print(f"Pending scrobbles in offline queue: {count}")
    elif args.flush:
        ok, n = scrobbler.flush_queue()
        print(f"Flush completed: {n} scrobbles submitted (Success: {ok})")
    else:
        scrobbler.run()
