import os
import sys
import json
import time
import signal
import logging
from datetime import datetime, timezone, timedelta

import boto3
from botocore.config import Config
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import mysql.connector

# ----------------------------
# Import Cloud Modules
# ----------------------------
from aws_module import (
    store_dummy_monthly_cost as aws_cost,
    collect_ec2_status,
)
from azure_module import (
    store_dummy_monthly_cost as azure_cost,
    store_dummy_server_status as azure_status,
)
from gcp_module import (
    store_dummy_monthly_cost as gcp_cost,
    store_dummy_server_status as gcp_status,
)

# ----------------------------
# Logging
# ----------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("worker")

# ----------------------------
# Config from env
# ----------------------------
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
SSM_PARAM_NAME = os.getenv("SSM_PARAM_NAME", "myapp_database_credentials")
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME", "appdb")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60000"))

if not DB_HOST:
    log.error("DB_HOST is required (RDS endpoint).")
    sys.exit(1)

# ----------------------------
# AWS Clients
# ----------------------------
boto_cfg = Config(retries={"max_attempts": 5, "mode": "standard"})
ssm = boto3.client("ssm", region_name=AWS_REGION, config=boto_cfg)

# ----------------------------
# Graceful shutdown
# ----------------------------
_shutdown = False
def _handle_signal(signum, frame):
    global _shutdown
    log.info(f"Received signal {signum}. Shutting down gracefully...")
    _shutdown = True

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)

# ----------------------------
# DB Connection
# ----------------------------
class TransientDBError(Exception):
    pass

@retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=20),
    retry=retry_if_exception_type(TransientDBError),
)
def get_db_connection():
    try:
        param = ssm.get_parameter(Name=SSM_PARAM_NAME, WithDecryption=True)
        creds = json.loads(param["Parameter"]["Value"])
        user = creds["username"]
        password = creds["password"]
    except Exception as e:
        log.exception("Failed to fetch DB creds from SSM.")
        raise

    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=user,
            password=password,
            autocommit=True,
            connection_timeout=10,
        )
        return conn
    except mysql.connector.Error as e:
        log.warning(f"MySQL connection error: {e}")
        raise TransientDBError(e)

# ----------------------------
# Table creation
# ----------------------------
def ensure_tables(conn):
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cloud_cost_monthly (
            cloud VARCHAR(32) NOT NULL,
            month_year VARCHAR(7) NOT NULL,
            service VARCHAR(128) NOT NULL,
            total_amount DECIMAL(18,2) NOT NULL,
            pct_of_total DECIMAL(5,2) NOT NULL,
            retrieved_at TIMESTAMP NOT NULL,
            PRIMARY KEY (cloud, month_year, service)
        ) ENGINE=InnoDB;
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS server_status_agg (
            cloud VARCHAR(32) NOT NULL,
            region VARCHAR(32) NOT NULL,
            az VARCHAR(32) NOT NULL,
            running INT NOT NULL,
            stopped INT NOT NULL,
            `terminated` INT NOT NULL,
            retrieved_at TIMESTAMP NOT NULL,
            PRIMARY KEY (cloud, region, az)
        ) ENGINE=InnoDB;
    """)
    
    conn.commit()
    cur.close()

# ----------------------------
# Utility: Print table rows
# ----------------------------
def print_table(conn, table_name):
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table_name} ORDER BY retrieved_at DESC LIMIT 20")
    rows = cur.fetchall()

    log.info(f"--- Last rows from {table_name} ---")
    print("\t".join([desc[0] for desc in cur.description]))
    for row in rows:
        print("\t".join(str(r) for r in row))
    cur.close()

# ----------------------------
# Main loop function 
# ----------------------------
def run_once():
    conn = get_db_connection()
    ensure_tables(conn)

    # ----------------------------
    # AWS (real/dummy mix, unchanged)
    # ----------------------------
    aws_cost(conn, cloud="AWS")
    collect_ec2_status(conn, cloud="AWS")

    # ----------------------------
    # Azure (dummy only)
    # ----------------------------
    azure_cost(conn, cloud="Azure")
    azure_status(conn, cloud="Azure")

    # ----------------------------
    # GCP (dummy only)
    # ----------------------------
    gcp_cost(conn, cloud="GCP")
    gcp_status(conn, cloud="GCP")

    # Debug print
    print_table(conn, "cloud_cost_monthly")
    print_table(conn, "server_status_agg")

    conn.close()


def main():
    while not _shutdown:
        run_once()
        if _shutdown:
            break
        log.info(f"Sleeping {POLL_INTERVAL_SECONDS}s before next run...")
        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
