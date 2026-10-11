import sqlite3
import os
import sys

# Allow importing from src if executed directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.db import get_db_connection, ensure_db_indexes

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
data_dir = os.path.join(PROJECT_ROOT, "data")
os.makedirs(data_dir, exist_ok=True)
db_path = os.path.join(data_dir, "conveyor_state.sqlite")
schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

print("Initializing database with WAL mode and indices...")
with get_db_connection(db_path) as conn:
    cursor = conn.cursor()
    with open(schema_path, "r", encoding="utf-8") as sql_file:
        cursor.executescript(sql_file.read())
    ensure_db_indexes(conn)

print("Database ready and optimized.")
