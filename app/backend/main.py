# main.py
import os
import uvicorn
from api.metrics import app

if __name__ == "__main__":
    host = os.environ.get("APP_HOST", "0.0.0.0")
    port = int(os.environ.get("APP_PORT", 8000))
    reload = os.environ.get("APP_RELOAD", "false").lower() == "true"

    print(f"\n Starting FastAPI server at: http://{host}:{port}")
    print(f" Swagger docs available at: http://{host}:{port}/docs")
    print(f" ReDoc docs available at:   http://{host}:{port}/redoc")
    print("\n--- Sample Endpoints ---")
    print(f" AWS Costs endpoint:        http://{host}:{port}/api/aws/costs")
    print(f" AWS Status endpoint:       http://{host}:{port}/api/aws/status")
    print(f" GCP Costs endpoint:        http://{host}:{port}/api/gcp/costs")
    print(f" Azure Status endpoint:     http://{host}:{port}/api/azure/status")
    print(f" All Clouds Costs endpoint: http://{host}:{port}/api/all/costs\n")

    uvicorn.run(
        "api.metrics:app",
        host=host,
        port=port,
        reload=reload
    )
