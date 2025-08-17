from fastapi import FastAPI, HTTPException, Query
from core.database import get_db_connection
from decimal import Decimal
import datetime

app = FastAPI(title="AWS Metrics API", version="2.0.0")

# -----------------------------
# Helpers
# -----------------------------
def serialize_value(value):
    """Convert Decimal and datetime objects to JSON-serializable format."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value

def fetch_table_rows(table_name: str, limit: int = 10):
    """Fetch latest rows from a given table dynamically."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name} ORDER BY retrieved_at DESC LIMIT %s", (limit,))
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        cursor.close()
        conn.close()

        return [
            {columns[i]: serialize_value(row[i]) for i in range(len(columns))}
            for row in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed for table {table_name}: {e}")

# -----------------------------
# API Endpoints
# -----------------------------
@app.get("/aws/costs")
def get_cloud_costs(limit: int = Query(10, gt=0, le=100)):
    """
    Fetch recent AWS monthly cloud costs.
    """
    return fetch_table_rows("cloud_cost_monthly", limit)

@app.get("/aws/ec2-status")
def get_server_status(limit: int = Query(10, gt=0, le=100)):
    """
    Fetch recent EC2 aggregated server status.
    """
    return fetch_table_rows("server_status_agg", limit)

@app.get("/aws/table/{table_name}")
def get_custom_table(table_name: str, limit: int = Query(10, gt=0, le=100)):
    """
    Fetch latest rows from any table dynamically.
    Useful for debugging or admin access.
    """
    return fetch_table_rows(table_name, limit)
