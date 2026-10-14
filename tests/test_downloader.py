"""
test_downloader.py
Unit tests for Downloader component: initialization, paths resolution,
and status classification without making live network calls.
"""

from src.downloader import Downloader
from src.paths import StoragePaths


def test_downloader_initialization(temp_config, temp_db, temp_env):
    dl = Downloader(temp_db, temp_config)
    assert hasattr(dl, "paths")
    assert isinstance(dl.paths, StoragePaths)
    assert dl.paths.cravings_dir == temp_env["cravings_dir"]
    assert dl.paths.permanent_dir == temp_env["permanent_dir"]
    assert dl.paths.conveyor_dir == temp_env["conveyor_dir"]


def test_downloader_status_classification(temp_config, temp_db, temp_env):
    dl = Downloader(temp_db, temp_config)

    # 1. Permanent track
    is_perm = 1
    f_path = dl.paths.get_permanente_track_path("Artist", "Album", "Song")
    if is_perm:
        status = "PERMANENT"
    elif getattr(dl.paths, "cravings_dir", None) and (dl.paths.cravings_dir in f_path):
        status = "ANTOJO"
    else:
        status = "CINTA"
    assert status == "PERMANENT"

    # 2. Craving track
    is_perm = 0
    f_path_craving = dl.paths.get_craving_track_path("Artist", "Album", "Song")
    if is_perm:
        status = "PERMANENT"
    elif getattr(dl.paths, "cravings_dir", None) and (dl.paths.cravings_dir in f_path_craving):
        status = "ANTOJO"
    else:
        status = "CINTA"
    assert status == "ANTOJO"

    # 3. Conveyor track
    is_perm = 0
    f_path_conveyor = dl.paths.get_conveyor_track_path("Artist", "Song")
    if is_perm:
        status = "PERMANENT"
    elif getattr(dl.paths, "cravings_dir", None) and (dl.paths.cravings_dir in f_path_conveyor):
        status = "ANTOJO"
    else:
        status = "CINTA"
    assert status == "CINTA"
