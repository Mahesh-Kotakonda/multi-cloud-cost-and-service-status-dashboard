# backend/core/database.py
import os
import psycopg2

def get_db_connection():
    """Create DB connection using env vars (username/password passed directly)."""
    host = os.environ.get("DB_HOST")
    port = int(os.environ.get("DB_PORT", 5432))
    dbname = os.environ.get("DB_NAME")
    user = os.environ.get("DB_USER")
    password = os.environ.get("DB_PASSWORD")

    if not all([host, dbname, user, password]):
        raise ValueError("DB_HOST, DB_NAME, DB_USER, and DB_PASSWORD must be set")

    conn = psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password
    )
    return conn
