from fastapi import FastAPI, HTTPException, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from core.database import get_db_connection
from decimal import Decimal
import datetime
import logging

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="Cloud Metrics API", version="2.0.0")

# ------------------------------
# CORS Setup
# -------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # since frontend & backend share ALB, relative URLs are safe
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Allowed tables / columns
# -----------------------------
# Only allow queries against known tables to avoid SQL injection via table_name
ALLOWED_TABLES = {
    "cloud_cost_monthly": {"date_column": "retrieved_at"},
    "server_status_agg": {"date_column": "retrieved_at"},
}

# Expected cloud values in DB (case-sensitive as stored). We'll compare uppercase.
ALLOWED_CLOUDS = {"AWS", "GCP", "AZURE", "ALL"}

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

def get_date_range(months_back: int = 2):
    """Return start and end datetime for last `months_back` months including current month."""
    today = datetime.datetime.utcnow()
    first_day_this_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Compute start month
    month = first_day_this_month.month - months_back
    year = first_day_this_month.year
    while month <= 0:
        month += 12
        year -= 1
    start_date = datetime.datetime(year, month, 1, 0, 0, 0)

    # End date is now (UTC)
    end_date = today

    return start_date, end_date

def fetch_table_rows_by_date(
    table_name: str,
    date_column: str = "retrieved_at",
    months_back: int = 2,
    cloud: str | None = None,
):
    """
    Fetch rows from an allowed table for the last `months_back` months including current month.
    Adds an optional cloud filter if cloud provided and not "ALL".
    """
    # Validate table name
    if table_name not in ALLOWED_TABLES:
        raise HTTPException(status_code=400, detail=f"Table '{table_name}' is not allowed.")

    # Validate date_column matches allowed for this table (prevent injection)
    allowed_date_col = ALLOWED_TABLES[table_name].get("date_column")
    if date_column != allowed_date_col:
        raise HTTPException(status_code=400, detail=f"Invalid date column for table '{table_name}'.")

    # Validate cloud parameter
    cloud_filter = None
    if cloud is not None:
        cloud_upper = cloud.strip().upper()
        if cloud_upper not in ALLOWED_CLOUDS:
            raise HTTPException(status_code=400, detail=f"Cloud must be one of {sorted(ALLOWED_CLOUDS)}")
        # If user passes 'ALL' we won't apply a cloud filter
        if cloud_upper != "ALL":
            # DB values appear to be "AWS", "GCP", "Azure" (logs show 'Azure' - case may vary)
            # We'll match DB value case-insensitively by comparing upper()
            cloud_filter = cloud_upper

    try:
        start_date, end_date = get_date_range(months_back)
        conn = get_db_connection()
        cursor = conn.cursor()

        # Build base query. Table name is inserted after validation.
        query = f"""
            SELECT *
            FROM {table_name}
            WHERE {date_column} >= %s AND {date_column} <= %s
        """
        params = [start_date, end_date]

        # If cloud_filter is set, add a case-insensitive filter on the cloud column
        if cloud_filter:
            # Use UPPER(cloud) = %s to be case-insensitive
            query += " AND UPPER(cloud) = %s"
            params.append(cloud_filter)

        query += f" ORDER BY {date_column} DESC"

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        cursor.close()
        conn.close()

        results = [
            {columns[i]: serialize_value(row[i]) for i in range(len(columns))}
            for row in rows
        ]

        return results
    except HTTPException:
        # re-raise HTTPExceptions (validation)
        raise
    except Exception as e:
        logger.exception("Query failed")
        raise HTTPException(status_code=500, detail=f"Query failed for table {table_name}: {e}")

# -----------------------------
# API Endpoints
# -----------------------------
# Backward-compatible endpoints for AWS (keeps your existing frontend working)
@app.get("/api/aws/costs")
def get_aws_cloud_costs(months_back: int = Query(2, ge=0, le=12)):
    """Fetch AWS monthly cloud costs (compatible legacy endpoint)."""
    return fetch_table_rows_by_date("cloud_cost_monthly", months_back=months_back, cloud="AWS")

@app.get("/api/aws/status")
def get_aws_server_status(months_back: int = Query(2, ge=0, le=12)):
    """Fetch AWS server status (compatible legacy endpoint)."""
    return fetch_table_rows_by_date("server_status_agg", months_back=months_back, cloud="AWS")

# Generic cloud endpoints: accepts path param cloud = aws|gcp|azure|all (case-insensitive)
@app.get("/api/{cloud}/costs")
def get_cloud_costs(
    cloud: str = Path(..., description="Cloud provider: aws | gcp | azure | all"),
    months_back: int = Query(2, ge=0, le=12),
):
    """Fetch cloud monthly costs for the named cloud (or all clouds)."""
    return fetch_table_rows_by_date("cloud_cost_monthly", months_back=months_back, cloud=cloud)

@app.get("/api/{cloud}/status")
def get_server_status(
    cloud: str = Path(..., description="Cloud provider: aws | gcp | azure | all"),
    months_back: int = Query(2, ge=0, le=12),
):
    """Fetch EC2/VM aggregated server status for the named cloud (or all clouds)."""
    return fetch_table_rows_by_date("server_status_agg", months_back=months_back, cloud=cloud)

# Administrative / generic table fetch (kept but safer)
@app.get("/api/table/{table_name}")
def get_custom_table(
    table_name: str = Path(..., description="Allowed table name"),
    months_back: int = Query(2, ge=0, le=12),
    date_column: str = Query("retrieved_at"),
    cloud: str | None = Query(None, description="Optional cloud filter: aws|gcp|azure|all"),
):
    """
    Fetch latest rows from an allowed table dynamically based on date range.
    Only allowed tables are supported (cloud_cost_monthly, server_status_agg).
    """
    return fetch_table_rows_by_date(table_name, date_column=date_column, months_back=months_back, cloud=cloud)
