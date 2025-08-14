import os
import time
import random
from datetime import datetime
from app.database.db import get_connection

INTERVAL_SECONDS = int(os.getenv("WORKER_INTERVAL", "60"))
RESOURCE_NAME = os.getenv("RESOURCE_NAME", "demo-resource")

def collect_and_store():
    cpu = round(random.uniform(0, 100), 2)
    mem = round(random.uniform(0, 100), 2)
    status = "healthy" if cpu < 80 and mem < 80 else "warning"

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO metrics (resource_name, cpu_usage, memory_usage, status, created_at)
        VALUES (%s, %s, %s, %s, %s);
        """,
        (RESOURCE_NAME, cpu, mem, status, datetime.utcnow())
    )
    conn.commit()
    conn.close()
    print(f"[{datetime.utcnow().isoformat()}] wrote metric cpu={cpu} mem={mem} status={status}")

if __name__ == "__main__":
    while True:
        try:
            collect_and_store()
        except Exception as e:
            print("Worker error:", e)
        time.sleep(INTERVAL_SECONDS)
