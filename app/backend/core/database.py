# backend/core/database.py
import os
import pymysql

def get_db_connection():
    """Create DB connection using env vars (MySQL)."""
    host = os.environ.get("DB_HOST")
    port = int(os.environ.get("DB_PORT", 3306))   # MySQL default
    dbname = os.environ.get("DB_NAME")
    user = os.environ.get("DB_USER")
    password = os.environ.get("DB_PASS")

    if not all([host, dbname, user, password]):
        raise ValueError("DB_HOST, DB_NAME, DB_USER, and DB_PASSWORD must be set")

    conn = pymysql.connect(
        host=host,
        port=port,
        db=dbname,
        user=user,
        password=password,
        cursorclass=pymysql.cursors.DictCursor
    )
    return conn
