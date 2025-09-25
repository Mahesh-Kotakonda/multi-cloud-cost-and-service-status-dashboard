import random
from datetime import datetime, timedelta
import boto3
from botocore.config import Config
import logging

log = logging.getLogger("aws")
boto_cfg = Config(retries={"max_attempts": 5, "mode": "standard"})
ec2 = boto3.client("ec2", config=boto_cfg)
ce = boto3.client("ce", config=boto_cfg)

# ----------------------------
# AWS Monthly Cost (dummy + real)
# ----------------------------
def store_dummy_monthly_cost(conn, cloud="AWS"):
    """
    Dummy cost generator for AWS (avoids Cost Explorer API charges).
    ⚠️ Replace with fetch_monthly_cost + store_monthly_cost for real-time.
    """
    today = datetime.utcnow()
    months = [
        (today.replace(day=1) - timedelta(days=61)).replace(day=1),
        (today.replace(day=1) - timedelta(days=31)).replace(day=1),
        today.replace(day=1)
    ]
    
    cur = conn.cursor()
    retrieved_at = datetime.utcnow()
    
    for month_start in months:
        month_str = month_start.strftime("%Y-%m")
        services = ["EC2", "S3", "RDS", "Lambda", "DynamoDB"]
        service_costs = {}
        total_amount = 0.0
        
        for s in services:
            cost = round(random.uniform(10, 100), 2)
            total_amount += cost
            service_costs[s] = cost
        
        service_costs_pct = {s: (c, round((c/total_amount)*100, 2)) for s, c in service_costs.items()}
        service_costs_pct['TOTAL'] = (total_amount, 100.0)
        
        rows = [
            (cloud, month_str, s, cost, pct, retrieved_at)
            for s, (cost, pct) in service_costs_pct.items()
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
        log.info(f"[AWS] Stored dummy costs for {month_str}")
    
    cur.close()

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
    log.info(f"[AWS] Stored {len(rows)} services for {cloud} - {month_year}")

# ----------------------------
# AWS EC2 Status
# ----------------------------
def fetch_and_aggregate_server_status_all_regions():
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
            rows.append(("AWS", region, az, counts['running'], counts['stopped'], counts['terminated'], retrieved_at))
            if region not in region_totals:
                region_totals[region] = {'running': 0, 'stopped': 0, 'terminated': 0}
            for k in counts:
                region_totals[region][k] += counts[k]

    for region, counts in region_totals.items():
        rows.append(("AWS", region, "TOTAL", counts['running'], counts['stopped'], counts['terminated'], retrieved_at))

    total_running = sum(counts['running'] for counts in region_totals.values())
    total_stopped = sum(counts['stopped'] for counts in region_totals.values())
    total_terminated = sum(counts['terminated'] for counts in region_totals.values())
    rows.append(("AWS", "ALL", "ALL", total_running, total_stopped, total_terminated, retrieved_at))

    return rows

def collect_ec2_status(conn):
    rows = fetch_and_aggregate_server_status_all_regions()
    store_server_status_agg(conn, rows)

def store_server_status_agg(conn, rows):
    cur = conn.cursor()
    cur.executemany("""
        INSERT INTO server_status_agg (cloud, region, az, running, stopped, `terminated`, retrieved_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            running=VALUES(running),
            stopped=VALUES(stopped),
            `terminated`=VALUES(`terminated`),
            retrieved_at=VALUES(retrieved_at)
    """, rows)

    conn.commit()
    cur.close()
    log.info(f"[AWS] Stored {len(rows)} aggregated server status rows")
