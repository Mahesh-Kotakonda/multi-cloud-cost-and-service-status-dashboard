from fastapi import FastAPI, HTTPException
from core.database import get_db_connection
from decimal import Decimal
import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AWS Metrics API")

def serialize_value(value):
    """Convert Decimal and datetime objects to JSON-serializable format."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value

def fetch_aws_costs(limit: int = 10):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
            SELECT cost_date, service, amount, unit, retrieved_at
            FROM aws_cost_daily
            ORDER BY cost_date DESC
            LIMIT %s
        """
        logger.info(f"Running query: {query.strip()} with limit={limit}")
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()

        cursor.close()
        conn.close()

        if not rows:
            raise HTTPException(status_code=404, detail="No AWS cost data found")

        return [
            {
                "cost_date": serialize_value(row[0]),
                "service": row[1],
                "amount": serialize_value(row[2]),
                "unit": row[3],
                "retrieved_at": serialize_value(row[4]),
            }
            for row in rows
        ]
    except Exception as e:
        logger.exception("AWS cost query failed")
        raise HTTPException(status_code=500, detail=f"AWS cost query failed: {str(e)}")

def fetch_ec2_status(limit: int = 10):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
            SELECT instance_id, az, state, system_status, instance_status, retrieved_bucket, retrieved_at
            FROM aws_ec2_instance_status
            ORDER BY retrieved_bucket DESC
            LIMIT %s
        """
        logger.info(f"Running query: {query.strip()} with limit={limit}")
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()

        cursor.close()
        conn.close()

        if not rows:
            raise HTTPException(status_code=404, detail="No EC2 status data found")

        return [
            {
                "instance_id": row[0],
                "az": row[1],
                "state": row[2],
                "system_status": row[3],
                "instance_status": row[4],
                "retrieved_bucket": serialize_value(row[5]),
                "retrieved_at": serialize_value(row[6]),
            }
            for row in rows
        ]
    except Exception as e:
        logger.exception("EC2 status query failed")
        raise HTTPException(status_code=500, detail=f"EC2 status query failed: {str(e)}")

@app.get("/aws/costs")
def get_aws_costs(limit: int = 10):
    return fetch_aws_costs(limit)

@app.get("/aws/ec2-status")
def get_ec2_status(limit: int = 10):
    return fetch_ec2_status(limit)
