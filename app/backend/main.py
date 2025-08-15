from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.database.db import get_connection
from app.backend.models import MetricIn, MetricOut
from typing import List

app = FastAPI(title="Multi-Cloud Metrics API")

# CORS for dev; tighten in prod
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # replace with your domain in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    # Simple DB connectivity probe
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        cur.fetchone()
        conn.close()
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return {"status": "degraded", "db_error": str(e)}

@app.get("/metrics", response_model=List[MetricOut])
def list_metrics(limit: int = 50):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, resource_name, cpu_usage, memory_usage, status, created_at
        FROM metrics
        ORDER BY created_at DESC
        LIMIT %s;
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

@app.post("/metrics", response_model=MetricOut, status_code=201)
def create_metric(metric: MetricIn):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO metrics (resource_name, cpu_usage, memory_usage, status)
        VALUES (%s, %s, %s, %s)
        RETURNING id, resource_name, cpu_usage, memory_usage, status, created_at;
        """,
        (metric.resource_name, metric.cpu_usage, metric.memory_usage, metric.status)
    )
    row = cur.fetchone()
    conn.commit()
    conn.close()
    if not row:
        raise HTTPException(status_code=500, detail="Insert failed")
    return row
