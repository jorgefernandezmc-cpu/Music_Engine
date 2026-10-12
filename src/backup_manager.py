"""
backup_manager.py
Smart unified backup engine for Music Engine:
- Automated snapshots on every engine run (controlled via backup.auto_backup in config).
- Single-file self-contained archives (.tar.gz bundles) containing database, auxiliary state, and manifest.
- Hot SQLite backup via sqlite3.backup() API (prevents WAL lock / corrupted reads).
- SHA-256 hash deduplication to avoid redundant snapshots when library state hasn't changed.
- Configurable backup directory, retention limits, and format options.
- Complete restore and cross-machine migration mechanism with automatic path rebasing and pre-restore safety snapshots.
"""

import os
import io
import json
import gzip
import shutil
import tarfile
import sqlite3
import hashlib
import logging
from datetime import datetime
from src.paths import StoragePaths
from src.db import get_db_connection

logger = logging.getLogger("backup")

CRITICAL_STATE_FILES = [
    "taste_profile.json",
    "download_archive.txt",
    "playlist_folder_state.json",
]


class BackupManager:
    """
    Manages automated and on-demand intelligent single-file backups and restorations
    for database state and environment configuration.
    """

    def __init__(self, db_path: str = "data/conveyor_state.sqlite", config_or_storage="config/config.yaml"):
        self.db_path = db_path
        if isinstance(config_or_storage, StoragePaths):
            self.paths = config_or_storage
            self.config = getattr(config_or_storage, "config", {}) or {}
        elif isinstance(config_or_storage, dict):
            self.paths = StoragePaths(config_or_storage)
            self.config = config_or_storage
        elif isinstance(config_or_storage, str) and os.path.exists(config_or_storage):
            self.paths = StoragePaths(config_or_storage)
            self.config = self.paths.config
        else:
            self.paths = StoragePaths("config/config.yaml")
            self.config = self.paths.config

        # Backup configuration
        backup_cfg = self.config.get("backup", {})
        
        # Target backup directory (supports ~ expansion, default: data/backups)
        configured_dir = backup_cfg.get("dir", self.config.get("storage", {}).get("backup_dir", "data/backups"))
        self.backup_dir = os.path.abspath(os.path.expanduser(configured_dir))

        # Max number of single-file snapshots to retain
        self.max_backups = int(backup_cfg.get("max_backups", self.config.get("storage", {}).get("max_db_backups", 10)))

        # Format: "bundle" (single .tar.gz containing everything) or "db_only" (.sqlite.gz)
        self.format = backup_cfg.get("format", "bundle").lower()

        # Automatic backup enabled on every engine run
        self.auto_backup_enabled = bool(backup_cfg.get("auto_backup", True))

        # Avoid redundant backups if database/state hash has not changed
        self.dedup_by_hash = bool(backup_cfg.get("dedup_by_hash", True))

        # Include runtime auxiliary state files (taste profile, download archive, playlist states)
        self.include_aux_files = bool(backup_cfg.get("include_aux_files", True))

        os.makedirs(self.backup_dir, exist_ok=True)

    def _calculate_db_hash(self) -> str:
        """
        Calculates a deterministic hash of database content by checkpointing WAL first.
        """
        if not os.path.exists(self.db_path):
            return ""

        try:
            with get_db_connection(self.db_path) as conn:
                conn.execute("PRAGMA wal_checkpoint(PASSIVE);")
        except Exception:
            pass

        hasher = hashlib.sha256()
        with open(self.db_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _get_last_hash_marker_path(self) -> str:
        """Returns path to state file tracking the last snapshot hash."""
        data_dir = os.path.dirname(self.db_path) or "data"
        return os.path.join(data_dir, ".last_backup_hash")

    def create_snapshot(self, tag: str = None, force: bool = False, output_path: str = None) -> str | None:
        """
        Creates an intelligent single-file snapshot of the entire music engine state:
        - Uses hot sqlite3 backup API so WAL mode never produces torn reads.
        - Creates a single unified archive (.tar.gz) containing DB, auxiliary state files, and manifest.
        - Dedupes identical backups using SHA-256 hash unless force=True.
        - Automatically rotates older snapshots according to max_backups.
        Returns: absolute path to the generated backup file, or None if skipped (deduped).
        """
        if not os.path.exists(self.db_path):
            logger.warning(f"Database not found at {self.db_path}. Skipping backup.")
            return None

        os.makedirs(self.backup_dir, exist_ok=True)

        # 1. Deduplication check
        current_hash = self._calculate_db_hash()
        last_hash_file = self._get_last_hash_marker_path()

        if not force and self.dedup_by_hash and os.path.exists(last_hash_file):
            try:
                with open(last_hash_file, "r", encoding="utf-8") as f:
                    last_hash = f.read().strip()
                if last_hash == current_hash:
                    logger.debug("Database state unchanged since last snapshot. Skipping duplicate backup.")
                    return None
            except Exception:
                pass

        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        tag_str = f"_{tag}" if tag else ""
        data_dir = os.path.dirname(self.db_path) or "data"

        # Determine target file path
        if output_path:
            target_file = os.path.abspath(os.path.expanduser(output_path))
            os.makedirs(os.path.dirname(target_file), exist_ok=True)
        else:
            ext = ".tar.gz" if self.format == "bundle" else ".sqlite.gz"
            filename = f"music_engine_backup_{now_str}{tag_str}{ext}"
            target_file = os.path.join(self.backup_dir, filename)

        # 2. Extract database in memory or temp file using SQLite hot backup API
        temp_hot_db = target_file + ".tmp.sqlite"
        try:
            src_conn = get_db_connection(self.db_path)
            dst_conn = sqlite3.connect(temp_hot_db)
            with src_conn, dst_conn:
                src_conn.backup(dst_conn)
            dst_conn.close()
            src_conn.close()

            # 3. Create SINGLE unified file based on format
            if self.format == "bundle" or target_file.endswith(".tar.gz") or target_file.endswith(".tgz"):
                with tarfile.open(target_file, "w:gz") as tar:
                    # A. Add hot database
                    tar.add(temp_hot_db, arcname="conveyor_state.sqlite")

                    # B. Add auxiliary files if present and enabled
                    if self.include_aux_files:
                        for aux_name in CRITICAL_STATE_FILES:
                            ap = os.path.join(data_dir, aux_name)
                            if os.path.exists(ap):
                                tar.add(ap, arcname=f"auxiliary/{aux_name}")

                    # C. Add self-describing manifest
                    manifest = {
                        "version": 2,
                        "created_at": datetime.now().isoformat(),
                        "tag": tag,
                        "db_sha256": current_hash,
                        "original_base_dir": self.paths.base_dir,
                        "conveyor_dir": self.paths.conveyor_dir,
                        "permanent_dir": self.paths.permanent_dir,
                        "playlists_dir": self.paths.playlists_dir,
                    }
                    m_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
                    ti = tarfile.TarInfo(name="manifest.json")
                    ti.size = len(m_bytes)
                    ti.mtime = int(datetime.now().timestamp())
                    tar.addfile(ti, io.BytesIO(m_bytes))
            else:
                # db_only format: single compressed .sqlite.gz
                with open(temp_hot_db, "rb") as f_in, gzip.open(target_file, "wb", compresslevel=6) as f_out:
                    shutil.copyfileobj(f_in, f_out)

            # 4. Record last backup hash marker
            try:
                with open(last_hash_file, "w", encoding="utf-8") as f:
                    f.write(current_hash)
            except Exception:
                pass

            logger.info(f"Smart single-file backup created: {target_file}")
            print(f"[BackupManager] Snapshot created: {os.path.basename(target_file)}")

            # 5. Rotate older snapshots if keeping within retention folder
            if not output_path:
                self.rotate_backups()

            return target_file

        finally:
            if os.path.exists(temp_hot_db):
                try:
                    os.remove(temp_hot_db)
                except Exception:
                    pass

    def list_backups(self) -> list[dict]:
        """
        Lists all available single-file snapshots in the backup directory with metadata, sizes, and timestamps.
        Reads manifests directly from tar.gz without extracting to disk.
        """
        if not os.path.exists(self.backup_dir):
            return []

        backups = []
        for fname in os.listdir(self.backup_dir):
            if fname.startswith("music_engine_backup_") and (fname.endswith(".tar.gz") or fname.endswith(".sqlite.gz") or fname.endswith(".sqlite")):
                full_p = os.path.join(self.backup_dir, fname)
                st = os.stat(full_p)

                meta_info = {}
                is_bundle = fname.endswith(".tar.gz") or fname.endswith(".tgz")

                if is_bundle:
                    try:
                        with tarfile.open(full_p, "r:gz") as tar:
                            try:
                                mf = tar.extractfile("manifest.json")
                                if mf:
                                    meta_info = json.loads(mf.read().decode("utf-8"))
                            except KeyError:
                                pass
                    except Exception:
                        pass

                tag = meta_info.get("tag")
                if not tag and "_" in fname:
                    parts = fname.rsplit(".", 2)[0].split("_")
                    if len(parts) >= 5:
                        tag = "_".join(parts[4:])

                backups.append({
                    "filename": fname,
                    "path": full_p,
                    "size_bytes": st.st_size,
                    "mtime": st.st_mtime,
                    "date": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "format": "bundle (.tar.gz)" if is_bundle else "database only",
                    "tag": tag,
                    "manifest": meta_info
                })

        backups.sort(key=lambda b: b["mtime"], reverse=True)
        return backups

    def rotate_backups(self):
        """
        Purges snapshots exceeding self.max_backups to maintain clean disk retention.
        """
        backups = self.list_backups()
        if len(backups) > self.max_backups:
            to_remove = backups[self.max_backups:]
            for b in to_remove:
                try:
                    os.remove(b["path"])
                    logger.debug(f"Rotated old backup: {b['filename']}")
                except Exception as e:
                    logger.warning(f"Could not remove old backup {b['filename']}: {e}")

    def export_full_bundle(self, output_path: str = None) -> str:
        """
        Exports a unified single-file migration bundle (.tar.gz) for moving to another PC.
        """
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not output_path:
            output_path = os.path.join(self.backup_dir, f"music_engine_backup_{now_str}_export.tar.gz")

        output_path = os.path.abspath(os.path.expanduser(output_path))
        exported_file = self.create_snapshot(tag="export", force=True, output_path=output_path)
        print(f"[BackupManager] Portable migration bundle exported: {exported_file}")
        return exported_file

    def restore_backup(self, backup_source: str, target_base_dir: str = None, rebase_paths: bool = True) -> dict:
        """
        Restores a single-file backup into the active environment:
        - Accepts unified .tar.gz bundle or raw .sqlite/.sqlite.gz.
        - Automatically creates a pre-restore safety snapshot before altering active data.
        - Automatically rebases file_path references in database if moving across PCs or new storage directory.
        """
        backup_source = os.path.abspath(os.path.expanduser(backup_source))
        if not os.path.exists(backup_source):
            raise FileNotFoundError(f"Backup file not found at: {backup_source}")

        # 1. Create safety snapshot of current state before touching anything
        if os.path.exists(self.db_path):
            print("[BackupManager] Creating pre-restore safety snapshot...")
            self.create_snapshot(tag="pre_restore_safety", force=True)

        data_dir = os.path.dirname(self.db_path) or "data"
        os.makedirs(data_dir, exist_ok=True)
        manifest = {}
        restored_files = []

        temp_extract_dir = os.path.join(data_dir, "_temp_restore")
        if os.path.exists(temp_extract_dir):
            shutil.rmtree(temp_extract_dir, ignore_errors=True)
        os.makedirs(temp_extract_dir, exist_ok=True)

        try:
            # Check if source is a .tar.gz bundle
            if tarfile.is_tarfile(backup_source):
                with tarfile.open(backup_source, "r:*") as tar:
                    tar.extractall(temp_extract_dir)

                # Read manifest
                mf_path = os.path.join(temp_extract_dir, "manifest.json")
                if os.path.exists(mf_path):
                    try:
                        with open(mf_path, "r", encoding="utf-8") as f:
                            manifest = json.load(f)
                    except Exception:
                        pass

                # Locate database inside archive
                db_cand = None
                for root, _, files in os.walk(temp_extract_dir):
                    for f in files:
                        if "conveyor_state" in f or f.endswith(".sqlite") or f.endswith(".sqlite.gz"):
                            db_cand = os.path.join(root, f)
                            break
                    if db_cand:
                        break

                if not db_cand:
                    raise ValueError("No SQLite database found inside migration archive.")

                # Extract/decompress sqlite into target db_path
                if db_cand.endswith(".gz"):
                    with gzip.open(db_cand, "rb") as f_in, open(self.db_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                else:
                    shutil.copy2(db_cand, self.db_path)
                restored_files.append("database")

                # Restore auxiliary files if present
                aux_dir = os.path.join(temp_extract_dir, "auxiliary")
                if os.path.exists(aux_dir):
                    for aux_f in os.listdir(aux_dir):
                        src_af = os.path.join(aux_dir, aux_f)
                        dst_af = os.path.join(data_dir, aux_f)
                        shutil.copy2(src_af, dst_af)
                        restored_files.append(aux_f)

            # Direct SQLite / Gzipped SQLite file
            elif backup_source.endswith(".gz"):
                with gzip.open(backup_source, "rb") as f_in, open(self.db_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                restored_files.append("database")
            else:
                shutil.copy2(backup_source, self.db_path)
                restored_files.append("database")

            # 2. Rebase file paths if moving to another computer or new base_dir
            new_base = os.path.abspath(os.path.expanduser(target_base_dir or self.paths.base_dir))
            old_base = manifest.get("original_base_dir")
            rebased_count = 0

            if rebase_paths:
                with get_db_connection(self.db_path) as conn:
                    cursor = conn.cursor()
                    if not old_base:
                        cursor.execute("SELECT file_path FROM tracks WHERE file_path IS NOT NULL LIMIT 50")
                        samples = [r[0] for r in cursor.fetchall() if r[0]]
                        if samples:
                            parts = [p.split("/Canciones/")[0] if "/Canciones/" in p else p.rsplit("/Permanent", 1)[0] for p in samples]
                            if parts:
                                old_base = parts[0]

                    if old_base and old_base != new_base:
                        print(f"[BackupManager] Rebasing file paths from '{old_base}' -> '{new_base}'...")
                        cursor.execute("""
                            UPDATE tracks 
                            SET file_path = REPLACE(file_path, ?, ?) 
                            WHERE file_path LIKE ?
                        """, (old_base, new_base, f"{old_base}%"))
                        rebased_count = cursor.rowcount
                        conn.commit()

            # Ensure schema indexes and integrity if standard columns exist
            try:
                from src.db import ensure_db_indexes
                with get_db_connection(self.db_path) as conn:
                    ensure_db_indexes(conn)
            except Exception as e:
                logger.debug(f"Index check skipped or partial: {e}")

            with get_db_connection(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM tracks")
                total_tracks = cursor.fetchone()[0]

            print(f"[BackupManager] Restore completed successfully! ({total_tracks} tracks restored, {rebased_count} paths rebased)")

            return {
                "success": True,
                "total_tracks": total_tracks,
                "rebased_count": rebased_count,
                "restored_components": restored_files,
                "old_base": old_base,
                "new_base": new_base
            }

        finally:
            if os.path.exists(temp_extract_dir):
                shutil.rmtree(temp_extract_dir, ignore_errors=True)
