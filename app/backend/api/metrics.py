from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from core.database import get_db_connection
from decimal import Decimal
import datetime
import logging

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="Cloud Metrics API", version="2.0.0")

# ------------------------------
# CORS Setup
# ------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Allowed tables
# -----------------------------
ALLOWED_TABLES = {
    "cloud_cost_monthly": {"date_column": "retrieved_at"},
    "server_status_agg": {"date_column": "retrieved_at"},
}

ALLOWED_CLOUDS = {"AWS", "GCP", "AZURE"}

# -----------------------------
# Helpers
# -----------------------------
def serialize_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value

def get_date_range(months_back: int = 2):
    today = datetime.datetime.utcnow()
    first_day_this_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    month = first_day_this_month.month - months_back
    year = first_day_this_month.year
    while month <= 0:
        month += 12
        year -= 1
    start_date = datetime.datetime(year, month, 1, 0, 0, 0)

    return start_date, today

def fetch_table_rows_by_date(
    table_name: str,
    date_column: str = "retrieved_at",
    months_back: int = 2,
    cloud: str | None = None,
):
    if table_name not in ALLOWED_TABLES:
        raise HTTPException(status_code=400, detail=f"Table '{table_name}' is not allowed.")

    allowed_date_col = ALLOWED_TABLES[table_name]["date_column"]
    if date_column != allowed_date_col:
        raise HTTPException(status_code=400, detail=f"Invalid date column for table '{table_name}'.")

    cloud_filter = None
    if cloud:
        cloud_upper = cloud.strip().upper()
        if cloud_upper not in ALLOWED_CLOUDS:
            raise HTTPException(status_code=400, detail=f"Cloud must be one of {sorted(ALLOWED_CLOUDS)}")
        cloud_filter = cloud_upper

    try:
        start_date, end_date = get_date_range(months_back)
        conn = get_db_connection()
        cursor = conn.cursor()

        query = f"""
            SELECT *
            FROM {table_name}
            WHERE {date_column} >= %s AND {date_column} <= %s
        """
        params = [start_date, end_date]

        if cloud_filter:
            query += " AND UPPER(cloud) = %s"
            params.append(cloud_filter)

        query += f" ORDER BY {date_column} DESC"

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        cursor.close()
        conn.close()

        return [
            {columns[i]: serialize_value(row[i]) for i in range(len(columns))}
            for row in rows
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Query failed")
        raise HTTPException(status_code=500, detail=f"Query failed for table {table_name}: {e}")

# -----------------------------
# Explicit Cloud Endpoints Only
# -----------------------------

# AWS
@app.get("/api/aws/costs")
def get_aws_costs(months_back: int = Query(2, ge=0, le=12)):
    return fetch_table_rows_by_date("cloud_cost_monthly", months_back=months_back, cloud="AWS")

@app.get("/api/aws/status")
def get_aws_status(months_back: int = Query(2, ge=0, le=12)):
    return fetch_table_rows_by_date("server_status_agg", months_back=months_back, cloud="AWS")

# Azure
@app.get("/api/azure/costs")
def get_azure_costs(months_back: int = Query(2, ge=0, le=12)):
    return fetch_table_rows_by_date("cloud_cost_monthly", months_back=months_back, cloud="AZURE")

@app.get("/api/azure/status")
def get_azure_status(months_back: int = Query(2, ge=0, le=12)):
    return fetch_table_rows_by_date("server_status_agg", months_back=months_back, cloud="AZURE")

# GCP
@app.get("/api/gcp/costs")
def get_gcp_costs(months_back: int = Query(2, ge=0, le=12)):
    return fetch_table_rows_by_date("cloud_cost_monthly", months_back=months_back, cloud="GCP")

@app.get("/api/gcp/status")
def get_gcp_status(months_back: int = Query(2, ge=0, le=12)):
    return fetch_table_rows_by_date("server_status_agg", months_back=months_back, cloud="GCP")

# -----------------------------
# Admin Endpoint (optional)
# -----------------------------
@app.get("/api/table/{table_name}")
def get_custom_table(
    table_name: str,
    months_back: int = Query(2, ge=0, le=12),
    date_column: str = Query("retrieved_at"),
    cloud: str | None = Query(None),
):
    return fetch_table_rows_by_date(table_name, date_column=date_column, months_back=months_back, cloud=cloud)
