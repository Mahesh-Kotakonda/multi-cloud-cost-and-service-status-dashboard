
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

import random
from datetime import datetime, timedelta

def store_dummy_monthly_cost(conn, cloud="AWS"):
    """
    Generate dummy cost data for the last 3 months and store in cloud_cost_monthly table.
    """
    today = datetime.utcnow()
    
    # Define 3 months: 2 months ago, 1 month ago, current month
    months = [
        (today.replace(day=1) - timedelta(days=61)).replace(day=1),
        (today.replace(day=1) - timedelta(days=31)).replace(day=1),
        today.replace(day=1)
    ]
    
    cur = conn.cursor()
    retrieved_at = datetime.utcnow()
    
    for month_start in months:
        month_str = month_start.strftime("%Y-%m")
        
        # Dummy services
        services = ["EC2", "S3", "RDS", "Lambda", "DynamoDB"]
        
        service_costs = {}
        total_amount = 0.0
        
        # Generate random dummy cost
        for s in services:
            cost = round(random.uniform(10, 100), 2)
            total_amount += cost
            service_costs[s] = cost
        
        # Calculate percentage of total
        service_costs_pct = {s: (c, round((c/total_amount)*100, 2)) for s, c in service_costs.items()}
        
        # Add TOTAL row
        service_costs_pct['TOTAL'] = (total_amount, 100.0)
        
        # Prepare rows for insertion
        rows = [
            (cloud, month_str, s, cost, pct, retrieved_at)
            for s, (cost, pct) in service_costs_pct.items()
        ]
        
        # Insert into DB
        cur.executemany("""
            INSERT INTO cloud_cost_monthly (cloud, month_year, service, total_amount, pct_of_total, retrieved_at)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                total_amount=VALUES(total_amount),
                pct_of_total=VALUES(pct_of_total),
                retrieved_at=VALUES(retrieved_at)
        """, rows)
        
        conn.commit()
        print(f"Stored dummy costs for {month_str}: {len(rows)} rows")
    
    cur.close()




# ----------------------------
# Logging (adjustable via env)
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
            region VARCHAR(32) NOT NULL,
            az VARCHAR(32) NOT NULL,
            running INT NOT NULL,
            stopped INT NOT NULL,
            `terminated` INT NOT NULL,
            retrieved_at TIMESTAMP NOT NULL,
            PRIMARY KEY (region, az)
        ) ENGINE=InnoDB;
    """)

    
    conn.commit()
    cur.close()

# ----------------------------
# Monthly cost helpers
# ----------------------------
def fetch_monthly_cost(ce_client, start_date, end_date):
    resp = ce_client.get_cost_and_usage(
        TimePeriod={"Start": start_date, "End": end_date},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )
    
    total = 0.0
    service_costs = {}
    
    for result in resp.get("ResultsByTime", []):
        for g in result.get("Groups", []):
            service = g["Keys"][0]
            amount = float(g["Metrics"]["UnblendedCost"]["Amount"])
            service_costs[service] = amount
            total += amount
    
    for s in service_costs:
        service_costs[s] = (service_costs[s], round((service_costs[s]/total)*100, 2))
    
    return service_costs, total

def store_monthly_cost(conn, cloud, month_year, service_costs):
    cur = conn.cursor()
    retrieved_at = datetime.utcnow()
    total_amount = sum(cost for cost, pct in service_costs.values())
    service_costs_with_total = {'TOTAL': (total_amount, 100.0)}
    service_costs_with_total.update(service_costs)
    
    rows = [
        (cloud, month_year, s, cost, pct, retrieved_at) 
        for s, (cost, pct) in service_costs_with_total.items()
    ]
    
    cur.executemany("""
        INSERT INTO cloud_cost_monthly (cloud, month_year, service, total_amount, pct_of_total, retrieved_at)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            total_amount=VALUES(total_amount),
            pct_of_total=VALUES(pct_of_total),
            retrieved_at=VALUES(retrieved_at)
    """, rows)
    
    conn.commit()
    cur.close()
    log.info(f"Stored {len(rows)} services for {cloud} - {month_year}")

# ----------------------------
# Server status helpers (updated for all regions)
# ----------------------------
def fetch_and_aggregate_server_status_all_regions():
    # Get all regions
    regions = [r['RegionName'] for r in ec2.describe_regions()['Regions']]
    
    agg = {}

    for region in regions:
        regional_client = boto3.client('ec2', region_name=region, config=boto_cfg)
        paginator = regional_client.get_paginator('describe_instances')

        for page in paginator.paginate():
            for reservation in page.get('Reservations', []):
                for instance in reservation.get('Instances', []):
                    az = instance['Placement']['AvailabilityZone']
                    state = instance['State']['Name'].lower()

                    if (region, az) not in agg:
                        agg[(region, az)] = {'running': 0, 'stopped': 0, 'terminated': 0}
                    if state in agg[(region, az)]:
                        agg[(region, az)][state] += 1

    retrieved_at = datetime.utcnow()
    rows = []
    region_totals = {}

    for (region, az), counts in agg.items():
        total_instances = counts['running'] + counts['stopped'] + counts['terminated']
        if total_instances > 0:
            rows.append((region, az, counts['running'], counts['stopped'], counts['terminated'], retrieved_at))
            if region not in region_totals:
                region_totals[region] = {'running': 0, 'stopped': 0, 'terminated': 0}
            for k in counts:
                region_totals[region][k] += counts[k]

    # Insert Region TOTAL rows
    for region, counts in region_totals.items():
        rows.append((region, 'TOTAL', counts['running'], counts['stopped'], counts['terminated'], retrieved_at))

    # Insert overall ALL row
    total_running = sum(counts['running'] for counts in region_totals.values())
    total_stopped = sum(counts['stopped'] for counts in region_totals.values())
    total_terminated = sum(counts['terminated'] for counts in region_totals.values())
    rows.append(('ALL', 'ALL', total_running, total_stopped, total_terminated, retrieved_at))

    return rows


def collect_ec2_status(conn):
    rows = fetch_and_aggregate_server_status_all_regions()
    store_server_status_agg(conn, rows)




def store_server_status_agg(conn, rows):
    cur = conn.cursor()
    cur.executemany("""
        INSERT INTO server_status_agg (region, az, running, stopped, `terminated`, retrieved_at)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            running=VALUES(running),
            stopped=VALUES(stopped),
            `terminated`=VALUES(`terminated`),
            retrieved_at=VALUES(retrieved_at)
    """, rows)

    conn.commit()
    cur.close()
    log.info(f"Stored {len(rows)} aggregated server status rows")

# ----------------------------
# Utility: Print table rows
# ----------------------------
def print_table(conn, table_name):
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table_name} ORDER BY retrieved_at DESC LIMIT 20")
    rows = cur.fetchall()

    log.info(f"--- Last rows from {table_name} ---")
    if table_name == "cloud_cost_monthly":
        headers = ["cloud", "month_year", "service", "total_amount", "pct_of_total", "retrieved_at"]
    elif table_name == "server_status_agg":
        headers = ["region", "az", "running", "stopped", "terminated", "retrieved_at"]
    else:
        headers = []

    print("\t".join(headers))
    for row in rows:
        print("\t".join(str(r) for r in row))
    cur.close()

# ----------------------------
# Main loop function 
# ----------------------------
# def run_once():
#     conn = get_db_connection()
#     ensure_tables(conn)

#     today = datetime.now(timezone.utc)
#     months = [
#         ((today.replace(day=1) - timedelta(days=61)).replace(day=1).strftime("%Y-%m-%d"),
#          (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m-%d")),
#         ((today.replace(day=1) - timedelta(days=31)).replace(day=1).strftime("%Y-%m-%d"),
#          (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m-%d")),
#         (today.replace(day=1).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")),
#     ]

#     for start, end in months:
#         month_str = datetime.strptime(start, "%Y-%m-%d").strftime("%Y-%m")
#         service_costs, total = fetch_monthly_cost(ce, start, end)
#         log.info(f"Month {month_str} total cost: {total:.2f} USD")
#         for s, (amt, pct) in service_costs.items():
#             log.info(f"  {s}: {amt:.2f} USD ({pct}%)")
#         store_monthly_cost(conn, 'AWS', month_str, service_costs)

#     collect_ec2_status(conn)

#     # Print last rows of both tables
#     print_table(conn, "cloud_cost_monthly")
#     print_table(conn, "server_status_agg")

#     conn.close()

def run_once():
    conn = get_db_connection()
    ensure_tables(conn)

    # --------------------------------------
    # 🔄 TEMPORARY: Use dummy cost generator
    # --------------------------------------
    # Instead of calling Cost Explorer API (which costs $0.01/request),
    # we insert random dummy cost values into the DB.
    # Later: Replace with fetch_monthly_cost() + store_monthly_cost().
    store_dummy_monthly_cost(conn, cloud="AWS")

    # --------------------------------------
    # EC2 Status Aggregation (kept as real calls)
    # --------------------------------------
    # This part is free (EC2 API calls are not billed), so we can run normally.
    collect_ec2_status(conn)

    # --------------------------------------
    # Print latest rows for debugging
    # --------------------------------------
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
