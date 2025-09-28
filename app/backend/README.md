# 🔗 Backend – REST APIs for Multi-Cloud Dashboard

The backend provides **REST APIs** that power the Multi-Cloud Dashboard.  
It connects to the database where the worker stores metrics and exposes them to the frontend.

---

## 🎯 Role in the System

- Serves **cost metrics** (current month + last 2 months)  
- Serves **server status** (region-wise & availability-zone-wise)  
- Provides a unified API layer for AWS, Azure, and GCP  
- Fetches data directly from the database populated by the worker  

---

## 🔌 API Endpoints

### AWS
- `/api/aws/costs` → Returns AWS cost metrics  
- `/api/aws/status` → Returns AWS server status  

### Azure
- `/api/azure/costs` → Returns Azure cost metrics  
- `/api/azure/status` → Returns Azure server status  

### GCP
- `/api/gcp/costs` → Returns GCP cost metrics  
- `/api/gcp/status` → Returns GCP server status  

---

## 📊 Data Flow

1. Worker fetches cloud data → Stores in DB  
2. Backend reads from DB → Exposes REST APIs  
3. Frontend consumes APIs → Displays in dashboard  

---

## 🛠️ Tech Stack

- **Python** – Flask / FastAPI (REST API framework)  
- **Database Integration** – PostgreSQL/MySQL (via SQLAlchemy or similar)  
- **Containerized** – Runs as a Docker container  

