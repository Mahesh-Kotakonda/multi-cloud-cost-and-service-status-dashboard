# gcp_module.py
import random
from datetime import datetime, timedelta
import logging

log = logging.getLogger("gcp")

def store_dummy_monthly_cost(conn, cloud="GCP"):
    """
    ✅ Dummy GCP Cost Data
    Generates random monthly cost data.
    ⚠️ Replace with GCP Billing API in the future.
    """
    today = datetime.utcnow()
    months = [
        (today.replace(day=1) - timedelta(days=61)).replace(day=1),
        (today.replace(day=1) - timedelta(days=31)).replace(day=1),
        today.replace(day=1)
    ]

    cur = conn.cursor()
    retrieved_at = datetime.utcnow()
    services = ["Compute Engine", "Cloud Storage", "BigQuery", "Cloud Functions", "Pub/Sub"]

    for month_start in months:
        month_str = month_start.strftime("%Y-%m")
        total_amount = 0.0
        service_costs = {}

        for s in services:
            cost = round(random.uniform(15, 150), 2)
            total_amount += cost
            service_costs[s] = cost

        service_costs_pct = {s: (c, round((c/total_amount)*100, 2)) for s, c in service_costs.items()}
        service_costs_pct['TOTAL'] = (total_amount, 100.0)

        rows = [(cloud, month_str, s, cost, pct, retrieved_at) for s, (cost, pct) in service_costs_pct.items()]

        cur.executemany("""
            INSERT INTO cloud_cost_monthly (cloud, month_year, service, total_amount, pct_of_total, retrieved_at)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                total_amount=VALUES(total_amount),
                pct_of_total=VALUES(pct_of_total),
                retrieved_at=VALUES(retrieved_at)
        """, rows)
        conn.commit()
        log.info(f"[GCP] Stored dummy cost data for {month_str}")

    cur.close()


def store_dummy_server_status(conn, cloud="GCP"):
    """
    ✅ Dummy GCP Server Status
    Generates random VM counts by region/az.
    ⚠️ Replace with real GCP Compute Engine API in future.
    """
    retrieved_at = datetime.utcnow()
    cur = conn.cursor()

    regions = ["us-central1", "europe-west1"]
    azs = ["a", "b", "c"]

    rows = []
    for r in regions:
        for az in azs:
            running = random.randint(3, 12)
            stopped = random.randint(0, 5)
            terminated = random.randint(0, 2)
            rows.append((cloud, r, f"{r}-{az}", running, stopped, terminated, retrieved_at))

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
    log.info(f"[GCP] Stored dummy server status data")
