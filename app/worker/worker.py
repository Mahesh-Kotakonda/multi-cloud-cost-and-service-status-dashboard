
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta, timezone

import boto3
from botocore.config import Config
from dateutil.parser import isoparse
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import mysql.connector

# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("worker")

# ----------------------------
# Config from env
# ----------------------------
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
SSM_PARAM_NAME = os.getenv("SSM_PARAM_NAME", "myapp_database_credentials")
DB_HOST = os.getenv("DB_HOST")  # REQUIRED
DB_NAME = os.getenv("DB_NAME", "appdb")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "600"))

if not DB_HOST:
    log.error("DB_HOST is required (RDS endpoint).")
    sys.exit(1)

# ----------------------------
# AWS Clients
# ----------------------------
boto_cfg = Config(retries={"max_attempts": 5, "mode": "standard"})
ssm = boto3.client("ssm", region_name=AWS_REGION, config=boto_cfg)
ec2 = boto3.client("ec2", region_name=AWS_REGION, config=boto_cfg)
ce = boto3.client("ce", region_name=AWS_REGION, config=boto_cfg)

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
# Secrets / DB connection
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
    """
    Fetches credentials from SSM and returns a live MySQL connection.
    Retries on transient connection errors.
    """
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
        # Treat network/auth errors as transient for retry
        log.warning(f"MySQL connection error: {e}")
        raise TransientDBError(e)

def ensure_schema(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS aws_cost_daily (
          cost_date DATE NOT NULL,
          service VARCHAR(128) NOT NULL,
          amount DECIMAL(18,8) NOT NULL,
          unit VARCHAR(16) NOT NULL,
          retrieved_at TIMESTAMP NOT NULL,
          PRIMARY KEY (cost_date, service)
        ) ENGINE=InnoDB;
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS aws_ec2_instance_status (
          instance_id VARCHAR(32) NOT NULL,
          az VARCHAR(32) NOT NULL,
          state VARCHAR(32) NOT NULL,
          system_status VARCHAR(32) NOT NULL,
          instance_status VARCHAR(32) NOT NULL,
          retrieved_bucket TIMESTAMP NOT NULL,
          retrieved_at TIMESTAMP NOT NULL,
          PRIMARY KEY (instance_id, retrieved_bucket),
          INDEX idx_bucket (retrieved_bucket)
        ) ENGINE=InnoDB;
    """)
    cur.close()

# ----------------------------
# Collectors
# ----------------------------
def time_bucket_10min(ts: datetime) -> datetime:
    """Round down to 10-minute buckets."""
    minute = (ts.minute // 10) * 10
    return ts.replace(minute=minute, second=0, microsecond=0)

@retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=20),
)
def collect_costs(conn):
    """
    Collect daily AWS cost per service for yesterday and today (USD).
    Cost Explorer has DAILY granularity; still safe to refresh every run.
    """
    now = datetime.now(timezone.utc).date()
    start = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    end = (now + timedelta(days=1)).strftime("%Y-%m-%d")  # CE end is exclusive

    resp = ce.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )

    rows = []
    retrieved_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    for result_by_time in resp.get("ResultsByTime", []):
        cost_date = result_by_time["TimePeriod"]["Start"]
        groups = result_by_time.get("Groups", [])
        for g in groups:
            service = g["Keys"][0]
            amount = g["Metrics"]["UnblendedCost"]["Amount"]
            unit = g["Metrics"]["UnblendedCost"]["Unit"]
            rows.append((cost_date, service, amount, unit, retrieved_at))

    if not rows:
        log.info("No cost rows returned from Cost Explorer.")
        return

    cur = conn.cursor()
    cur.executemany(
        """
        INSERT INTO aws_cost_daily (cost_date, service, amount, unit, retrieved_at)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          amount = VALUES(amount),
          unit = VALUES(unit),
          retrieved_at = VALUES(retrieved_at)
        """,
        rows,
    )
    cur.close()
    log.info(f"Upserted {len(rows)} cost rows.")

@retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=20),
)
def collect_ec2_status(conn):
    """
    Collect EC2 state + detailed status for all instances in the region.
    """
    instances = []
    paginator = ec2.get_paginator("describe_instances")
    for page in paginator.paginate():
        for r in page.get("Reservations", []):
            for i in r.get("Instances", []):
                instances.append({
                    "InstanceId": i["InstanceId"],
                    "Az": i.get("Placement", {}).get("AvailabilityZone", "unknown"),
                    "State": i.get("State", {}).get("Name", "unknown"),
                })

    # describe_instance_status returns detailed checks; need IncludeAllInstances=True
    detail = {}
    paginator = ec2.get_paginator("describe_instance_status")
    for page in paginator.paginate(IncludeAllInstances=True):
        for s in page.get("InstanceStatuses", []):
            iid = s["InstanceId"]
            detail[iid] = {
                "SystemStatus": s.get("SystemStatus", {}).get("Status", "unknown"),
                "InstanceStatus": s.get("InstanceStatus", {}).get("Status", "unknown"),
            }

    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    bucket = time_bucket_10min(now).strftime("%Y-%m-%d %H:%M:%S")
    retrieved_at = now.strftime("%Y-%m-%d %H:%M:%S")

    rows = []
    for ins in instances:
        iid = ins["InstanceId"]
        rows.append((
            iid,
            ins["Az"],
            ins["State"],
            detail.get(iid, {}).get("SystemStatus", "unknown"),
            detail.get(iid, {}).get("InstanceStatus", "unknown"),
            bucket,
            retrieved_at,
        ))

    if not rows:
        log.info("No EC2 instances found.")
        return

    cur = conn.cursor()
    cur.executemany(
        """
        INSERT INTO aws_ec2_instance_status
        (instance_id, az, state, system_status, instance_status, retrieved_bucket, retrieved_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          az = VALUES(az),
          state = VALUES(state),
          system_status = VALUES(system_status),
          instance_status = VALUES(instance_status),
          retrieved_at = VALUES(retrieved_at)
        """,
        rows,
    )
    cur.close()
    log.info(f"Upserted {len(rows)} EC2 status rows.")

# ----------------------------
# Main loop
# ----------------------------

def print_all_db_rows(conn):
    """
    Prints all rows from aws_cost_daily and aws_ec2_instance_status tables.
    """
    cur = conn.cursor(dictionary=True)

    # Print aws_cost_daily
    print("\n--- aws_cost_daily ---")
    cur.execute("SELECT * FROM aws_cost_daily ORDER BY cost_date, service")
    rows = cur.fetchall()
    if rows:
        for row in rows:
            print(row)
    else:
        print("No rows found in aws_cost_daily.")

    # Print aws_ec2_instance_status
    print("\n--- aws_ec2_instance_status ---")
    cur.execute("SELECT * FROM aws_ec2_instance_status ORDER BY retrieved_bucket, instance_id")
    rows = cur.fetchall()
    if rows:
        for row in rows:
            print(row)
    else:
        print("No rows found in aws_ec2_instance_status.")

    cur.close()

def run_once():
    conn = get_db_connection()
    try:
        ensure_schema(conn)
        collect_costs(conn)
        collect_ec2_status(conn)
        # Print all DB rows after collection
        print_all_db_rows(conn)
    finally:
        try:
            conn.close()
        except Exception:
            pass

def main():
    log.info("Worker starting...")
    log.info(f"AWS_REGION={AWS_REGION} DB_HOST={DB_HOST} DB_NAME={DB_NAME} PARAM={SSM_PARAM_NAME} interval={POLL_INTERVAL_SECONDS}s")

    while not _shutdown:
        start = time.time()
        try:
            run_once()
        except Exception as e:
            log.exception("Run failed, will retry next interval.")
        # sleep remainder of interval, responsive to shutdown
        elapsed = time.time() - start
        sleep_for = max(1, POLL_INTERVAL_SECONDS - int(elapsed))
        for _ in range(sleep_for):
            if _shutdown:
                break
            time.sleep(1)

    log.info("Worker stopped. Bye.")

if __name__ == "__main__":
    main()
