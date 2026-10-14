"""
test_paths.py
Unit tests for StoragePaths and path sanitization.
"""

import os
import yaml
from src.paths import StoragePaths, sanitize_filename, DEFAULT_REQUESTS_HEADER_EN, DEFAULT_REQUESTS_HEADER_ES


def test_sanitize_filename():
    assert sanitize_filename("Artist / Title") == "Artist - Title"
    assert sanitize_filename("What? *No*") == "What- -No-"
    assert sanitize_filename("...Leading and Trailing... ") == "Leading and Trailing"
    assert sanitize_filename("") == "Unknown"
    assert sanitize_filename("AC/DC") == "AC-DC"


def test_storage_paths_resolution(temp_config, temp_env):
    paths = StoragePaths(temp_config)
    assert paths.base_dir == temp_env["base_dir"]
    assert paths.conveyor_dir == temp_env["conveyor_dir"]
    assert paths.permanent_dir == temp_env["permanent_dir"]
    assert paths.cravings_dir == temp_env["cravings_dir"]
    assert paths.playlists_dir == temp_env["playlists_dir"]


def test_primary_artist_path(temp_config, temp_env):
    paths = StoragePaths(temp_config)
    perm_path = paths.get_permanente_track_path("Quevedo", "Donde Quiero Estar", "Columbia")
    expected_suffix = os.path.join("Permanent", "Quevedo", "Donde Quiero Estar", "Quevedo - Columbia.opus")
    assert perm_path.endswith(expected_suffix)
    assert perm_path.startswith(temp_env["base_dir"])


def test_cravings_and_conveyor_path(temp_config, temp_env):
    paths = StoragePaths(temp_config)
    craving_path = paths.get_craving_track_path("Duki", "Ameri", "Nueva Era")
    expected_craving = os.path.join("Cravings", "Duki", "Ameri", "Duki - Nueva Era.opus")
    assert craving_path.endswith(expected_craving)

    conveyor_path = paths.get_conveyor_track_path("Bizarrap", "Session 50")
    expected_conveyor = os.path.join("Conveyor", "Bizarrap - Session 50.opus")
    assert conveyor_path.endswith(expected_conveyor)


def test_mailbox_header_sync_bilingual(temp_config, temp_env):
    paths = StoragePaths(temp_config)
    req_file = paths.requests_file

    # Initially write header in English plus a pending user command
    user_command = 'Download "Columbia" by Quevedo\n'
    with open(req_file, "w", encoding="utf-8") as f:
        f.write(DEFAULT_REQUESTS_HEADER_EN + "\n" + user_command)

    # Change language to Spanish in config
    with open(temp_config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["system"]["language"] = "es"
    with open(temp_config, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f)

    # Re-instantiate and sync
    paths_es = StoragePaths(temp_config)
    paths_es.sync_mailbox_header()

    with open(req_file, "r", encoding="utf-8") as f:
        new_content = f.read()

    assert "BUZÓN REMOTO DE PETICIONES Y COMANDOS" in new_content
    assert "REMOTE REQUESTS AND COMMANDS MAILBOX" not in new_content
    assert user_command.strip() in new_content
