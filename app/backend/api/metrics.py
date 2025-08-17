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

def get_date_range(months_back: int = 2):
    """Return start date from `months_back` months ago until today."""
    today = datetime.date.today()
    first_day_this_month = today.replace(day=1)
    # subtract `months_back` months
    month = first_day_this_month.month - months_back
    year = first_day_this_month.year
    while month <= 0:
        month += 12
        year -= 1
    start_date = datetime.date(year, month, 1)
    end_date = today
    return start_date, end_date

def fetch_table_rows_by_date(table_name: str, date_column: str = "retrieved_at", months_back: int = 2):
    """Fetch rows from a table for the last `months_back` months including current month."""
    try:
        start_date, end_date = get_date_range(months_back)
        conn = get_db_connection()
        cursor = conn.cursor()
        query = f"""
            SELECT * FROM {table_name}
            WHERE {date_column} >= %s AND {date_column} <= %s
            ORDER BY {date_column} DESC
        """
        cursor.execute(query, (start_date, end_date))
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
def get_cloud_costs(months_back: int = Query(2, ge=0, le=12)):
    """
    Fetch AWS monthly cloud costs for the current month and previous `months_back` months.
    """
    return fetch_table_rows_by_date("cloud_cost_monthly", months_back=months_back)

@app.get("/aws/ec2-status")
def get_server_status(months_back: int = Query(2, ge=0, le=12)):
    """
    Fetch EC2 aggregated server status for the current month and previous `months_back` months.
    """
    return fetch_table_rows_by_date("server_status_agg", months_back=months_back)

@app.get("/aws/table/{table_name}")
def get_custom_table(table_name: str, months_back: int = Query(2, ge=0, le=12), date_column: str = Query("retrieved_at")):
    """
    Fetch latest rows from any table dynamically based on date range.
    """
    return fetch_table_rows_by_date(table_name, date_column=date_column, months_back=months_back)
