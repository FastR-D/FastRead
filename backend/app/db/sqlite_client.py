import sqlite3

from app.core.settings import get_settings

def get_connection():
    return sqlite3.connect(get_settings().sqlite_db_path)
