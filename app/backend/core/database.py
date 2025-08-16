# backend/core/database.py
import os
import psycopg2

def get_db_connection():
    """Create DB connection using environment variables."""
    host = os.getenv("DB_HOST")       # REQUIRED
    port = int(os.getenv("DB_PORT", 5432))
    dbname = os.getenv("DB_NAME")     # REQUIRED
    user = os.getenv("DB_USER")       # REQUIRED
    password = os.getenv("DB_PASSWORD")  # REQUIRED

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
