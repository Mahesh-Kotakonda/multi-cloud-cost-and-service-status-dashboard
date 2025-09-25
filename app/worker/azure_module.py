import random
from datetime import datetime, timedelta
import logging

log = logging.getLogger("azure")

# ----------------------------
# Azure Monthly Cost (Dummy)
# ----------------------------
def store_dummy_monthly_cost(conn, cloud="Azure"):
    """
    Dummy Azure Cost Data.
    ⚠️ Replace with Azure Cost Management API in the future.
    """
    today = datetime.utcnow()
    months = [
        (today.replace(day=1) - timedelta(days=61)).replace(day=1),
        (today.replace(day=1) - timedelta(days=31)).replace(day=1),
        today.replace(day=1),
    ]

    cur = conn.cursor()
    retrieved_at = datetime.utcnow()
    services = ["VM", "Storage", "SQL Database", "App Service", "Functions"]

    for month_start in months:
        month_str = month_start.strftime("%Y-%m")
        total_amount = 0.0
        service_costs = {}

        for s in services:
            cost = round(random.uniform(20, 200), 2)
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
        log.info(f"[{cloud}] Stored dummy cost data for {month_str}")

    cur.close()


# ----------------------------
# Azure Server Status (Dummy)
# ----------------------------
def store_dummy_server_status(conn, cloud="Azure"):
    """
    Dummy Azure Server Status.
    ⚠️ Replace with Azure Resource Manager API in the future.
    """
    retrieved_at = datetime.utcnow()
    cur = conn.cursor()

    regions = ["eastus", "westeurope"]
    azs = ["1", "2", "3"]

    rows = []
    region_totals = {}

    # per-availability zone rows
    for r in regions:
        for az in azs:
            running = random.randint(5, 15)
            stopped = random.randint(1, 5)
            terminated = random.randint(0, 3)
            rows.append(
                (cloud, r, f"{r}{az}", running, stopped, terminated, retrieved_at)
            )
            if r not in region_totals:
                region_totals[r] = {"running": 0, "stopped": 0, "terminated": 0}
            region_totals[r]["running"] += running
            region_totals[r]["stopped"] += stopped
            region_totals[r]["terminated"] += terminated

    # region totals
    for r, counts in region_totals.items():
        rows.append(
            (cloud, r, "TOTAL", counts["running"], counts["stopped"], counts["terminated"], retrieved_at)
        )

    # all-Azure total
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
