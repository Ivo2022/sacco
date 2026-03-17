import sqlite3
import os

DB = os.getenv("USERS_DB", "backend/users.db")

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn
