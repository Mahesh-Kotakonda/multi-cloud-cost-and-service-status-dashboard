import os
import random
from datetime import datetime, timedelta
import boto3
from botocore.config import Config
import logging

# ----------------------------
# Logging
# ----------------------------
log = logging.getLogger("aws")

# ----------------------------
# AWS Clients (region-aware)
# ----------------------------
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

boto_cfg = Config(retries={"max_attempts": 5, "mode": "standard"})
ec2 = boto3.client("ec2", region_name=AWS_REGION, config=boto_cfg)
ce = boto3.client("ce", region_name=AWS_REGION, config=boto_cfg)

# ----------------------------
# AWS Monthly Cost (dummy + real)
# ----------------------------

def store_dummy_monthly_cost(conn, cloud="AWS"):
    """
    Dummy cost generator for AWS with total < $10.
    ⚠️ Replace with fetch_monthly_cost + store_monthly_cost for real-time.
    """
    today = datetime.utcnow()
    months = [
        (today.replace(day=1) - timedelta(days=61)).replace(day=1),
        (today.replace(day=1) - timedelta(days=31)).replace(day=1),
        today.replace(day=1),
    ]

    cur = conn.cursor()
    retrieved_at = datetime.utcnow()

    for month_start in months:
        month_str = month_start.strftime("%Y-%m")
        services = ["EC2", "S3", "RDS", "Lambda", "DynamoDB"]

        # Generate random weights for services
        weights = [random.random() for _ in services]
        total_weight = sum(weights)

        # Fix total monthly budget under 10 (e.g., 9.xx)
        total_amount = round(random.uniform(8.5, 9.99), 2)

        # Allocate costs proportionally to weights
        service_costs = {}
        for s, w in zip(services, weights):
            cost = (w / total_weight) * total_amount
            service_costs[s] = round(cost, 2)

        # Ensure rounding doesn’t break total — adjust last service
        diff = total_amount - sum(service_costs.values())
        if abs(diff) >= 0.01:
            last_service = services[-1]
            service_costs[last_service] = round(service_costs[last_service] + diff, 2)

        # Calculate percentages
        service_costs_pct = {
            s: (c, round((c / total_amount) * 100, 2)) for s, c in service_costs.items()
        }
        service_costs_pct["TOTAL"] = (total_amount, 100.0)

        # Prepare rows
        rows = [
            (cloud, month_str, s, cost, pct, retrieved_at)
            for s, (cost, pct) in service_costs_pct.items()
        ]

        # Insert into DB
        cur.executemany(
            """
            INSERT INTO cloud_cost_monthly (cloud, month_year, service, total_amount, pct_of_total, retrieved_at)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                total_amount=VALUES(total_amount),
                pct_of_total=VALUES(pct_of_total),
                retrieved_at=VALUES(retrieved_at)
        """,
            rows,
        )
        conn.commit()
        log.info(f"[{cloud}] Stored dummy costs for {month_str}: total={total_amount}")

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
        service_costs[s] = (
            service_costs[s],
            round((service_costs[s] / total) * 100, 2),
        )

    return service_costs, total


def store_monthly_cost(conn, cloud, month_year, service_costs):
    cur = conn.cursor()
    retrieved_at = datetime.utcnow()
    total_amount = sum(cost for cost, pct in service_costs.values())
    service_costs_with_total = {"TOTAL": (total_amount, 100.0)}
    service_costs_with_total.update(service_costs)

    rows = [
        (cloud, month_year, s, cost, pct, retrieved_at)
        for s, (cost, pct) in service_costs_with_total.items()
    ]

    cur.executemany(
        """
        INSERT INTO cloud_cost_monthly (cloud, month_year, service, total_amount, pct_of_total, retrieved_at)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            total_amount=VALUES(total_amount),
            pct_of_total=VALUES(pct_of_total),
            retrieved_at=VALUES(retrieved_at)
    """,
        rows,
    )

    conn.commit()
    cur.close()
    log.info(f"[{cloud}] Stored {len(rows)} services for {month_year}")


# ----------------------------
# AWS EC2 Status
# ----------------------------
def fetch_and_aggregate_server_status_all_regions(cloud="AWS"):
    regions = [r["RegionName"] for r in ec2.describe_regions()["Regions"]]
    agg = {}

    for region in regions:
        regional_client = boto3.client(
            "ec2", region_name=region, config=boto_cfg
        )
        paginator = regional_client.get_paginator("describe_instances")

        for page in paginator.paginate():
            for reservation in page.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    az = instance["Placement"]["AvailabilityZone"]
                    state = instance["State"]["Name"].lower()

                    if (region, az) not in agg:
                        agg[(region, az)] = {
                            "running": 0,
                            "stopped": 0,
                            "terminated": 0,
                        }
                    if state in agg[(region, az)]:
                        agg[(region, az)][state] += 1

    retrieved_at = datetime.utcnow()
    rows = []
    region_totals = {}

    for (region, az), counts in agg.items():
        total_instances = (
            counts["running"] + counts["stopped"] + counts["terminated"]
        )
        if total_instances > 0:
            rows.append(
                (
                    cloud,
                    region,
                    az,
                    counts["running"],
                    counts["stopped"],
                    counts["terminated"],
                    retrieved_at,
                )
            )
            if region not in region_totals:
                region_totals[region] = {
                    "running": 0,
                    "stopped": 0,
                    "terminated": 0,
                }
            for k in counts:
                region_totals[region][k] += counts[k]

    for region, counts in region_totals.items():
        rows.append(
            (
                cloud,
                region,
                "TOTAL",
                counts["running"],
                counts["stopped"],
                counts["terminated"],
                retrieved_at,
            )
        )

    total_running = sum(counts["running"] for counts in region_totals.values())
    total_stopped = sum(counts["stopped"] for counts in region_totals.values())
    total_terminated = sum(
        counts["terminated"] for counts in region_totals.values()
    )
    rows.append(
        (
            cloud,
            "ALL",
            "ALL",
            total_running,
            total_stopped,
            total_terminated,
            retrieved_at,
        )
    )

    return rows


def collect_ec2_status(conn, cloud="AWS"):
    rows = fetch_and_aggregate_server_status_all_regions(cloud=cloud)
    store_server_status_agg(conn, rows, cloud=cloud)


def store_server_status_agg(conn, rows, cloud="AWS"):
    cur = conn.cursor()
    cur.executemany(
        """
        INSERT INTO server_status_agg (cloud, region, az, running, stopped, `terminated`, retrieved_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            running=VALUES(running),
            stopped=VALUES(stopped),
            `terminated`=VALUES(`terminated`),
            retrieved_at=VALUES(retrieved_at)
    """,
        rows,
    )

    conn.commit()
    cur.close()
    log.info(f"[{cloud}] Stored {len(rows)} aggregated server status rows")
