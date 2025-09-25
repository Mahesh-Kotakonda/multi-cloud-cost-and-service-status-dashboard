import random
from datetime import datetime, timedelta
import logging

log = logging.getLogger("gcp")

# ----------------------------
# GCP Monthly Cost (Dummy)
# ----------------------------
def store_dummy_monthly_cost(conn, cloud="GCP"):
    """
    Dummy GCP monthly cost data.
    ⚠️ Replace with GCP Billing API in the future.
    """
    today = datetime.utcnow()
    months = [
        (today.replace(day=1) - timedelta(days=61)).replace(day=1),
        (today.replace(day=1) - timedelta(days=31)).replace(day=1),
        today.replace(day=1),
    ]

    cur = conn.cursor()
    retrieved_at = datetime.utcnow()

    services = ["Compute Engine", "Cloud Storage", "BigQuery", "Cloud SQL", "Cloud Functions"]

    for month_start in months:
        month_str = month_start.strftime("%Y-%m")
        total_amount = 0.0
        service_costs = {}

        for s in services:
            cost = round(random.uniform(5, 80), 2)
            total_amount += cost
            service_costs[s] = cost

        service_costs_pct = {
            s: (c, round((c / total_amount) * 100, 2))
            for s, c in service_costs.items()
        }
        service_costs_pct["TOTAL"] = (total_amount, 100.0)

        rows = [
            (cloud, month_str, s, cost, pct, retrieved_at)
            for s, (cost, pct) in service_costs_pct.items()
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
        log.info(f"[{cloud}] Stored dummy costs for {month_str}: {len(rows)} rows")

    cur.close()


# ----------------------------
# GCP Server Status (Dummy)
# ----------------------------
def store_dummy_server_status(conn, cloud="GCP"):
    """
    Dummy GCP server status data.
    ⚠️ Replace with GCP Compute Engine API in the future.
    """
    cur = conn.cursor()
    retrieved_at = datetime.utcnow()

    # Dummy regions and zones
    regions = {
        "us-central1": ["us-central1-a", "us-central1-b"],
        "europe-west1": ["europe-west1-b", "europe-west1-c"],
    }

    rows = []
    region_totals = {}

    for region, zones in regions.items():
        for zone in zones:
            running = random.randint(0, 10)
            stopped = random.randint(0, 5)
            terminated = random.randint(0, 3)

            rows.append((cloud, region, zone, running, stopped, terminated, retrieved_at))

            if region not in region_totals:
                region_totals[region] = {"running": 0, "stopped": 0, "terminated": 0}
            region_totals[region]["running"] += running
            region_totals[region]["stopped"] += stopped
            region_totals[region]["terminated"] += terminated

    # region totals
    for region, counts in region_totals.items():
        rows.append(
            (cloud, region, "TOTAL", counts["running"], counts["stopped"], counts["terminated"], retrieved_at)
        )

    # all-GCP totals
    total_running = sum(c["running"] for c in region_totals.values())
    total_stopped = sum(c["stopped"] for c in region_totals.values())
    total_terminated = sum(c["terminated"] for c in region_totals.values())
    rows.append((cloud, "ALL", "ALL", total_running, total_stopped, total_terminated, retrieved_at))

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
    log.info(f"[{cloud}] Stored {len(rows)} dummy server status rows")
