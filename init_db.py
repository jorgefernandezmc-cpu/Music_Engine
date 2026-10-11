import sqlite3
import os

os.makedirs("data", exist_ok=True)
db_path = "data/conveyor_state.sqlite"

print("Inicializando base de datos...")
with sqlite3.connect(db_path) as conn:
    cursor = conn.cursor()
    with open("schema.sql", "r") as sql_file:
        cursor.executescript(sql_file.read())
print("Base de datos lista.")
