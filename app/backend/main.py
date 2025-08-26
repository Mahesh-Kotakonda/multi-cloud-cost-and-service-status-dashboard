# main.py
import os
import uvicorn
from api.metrics import app

if __name__ == "__main__":
    host = os.environ.get("APP_HOST", "0.0.0.0")
    port = int(os.environ.get("APP_PORT", 8000))
    reload = os.environ.get("APP_RELOAD", "false").lower() == "true"

    print(f"\n🚀 Starting FastAPI server at: http://{host}:{port}")
    print(f"📖 Swagger docs available at: http://{host}:{port}/docs")
    print(f"ReDoc docs available at:   http://{host}:{port}/redoc")
    print(f"💰 AWS Costs endpoint:        http://{host}:{port}/aws/costs")
    print(f"🖥️  EC2 Status endpoint:      http://{host}:{port}/aws/ec2-status\n")

    uvicorn.run(
        "api.metrics:app",
        host=host,
        port=port,
        reload=reload
    )
