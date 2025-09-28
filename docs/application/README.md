# 🖥️ Application Overview

The **Multi-Cloud Cost & Service Status Dashboard** is built as a containerized web application.  
It consists of three main components — **frontend, backend, and worker** — supported by a **database**.

---

## 📊 Components

### 1. Frontend (ReactJS)
- Provides the **web dashboard UI**.  
- Users can:
  - Select a cloud provider (AWS, Azure, GCP).  
  - View **cost metrics** (current month + last two months).  
  - View **server status** (region-wise and availability-zone-wise).  
- Runs as a **Docker container** and connects to the backend APIs.

---

### 2. Backend (Python APIs)
- Exposes **REST APIs** for the frontend.  
- Fetches data from the database and serves it to the UI.  
- Example endpoints:
  - `/api/aws/costs`
  - `/api/aws/status`
  - `/api/azure/costs`
  - `/api/gcp/status`  

---

### 3. Worker (Python)
- Independent container that **collects metrics** from cloud accounts and stores them in the database.  
- **AWS** → Fetches **live dynamic data** using SDKs.  
- **Azure & GCP** → Generates **dummy but realistic data** via functions (can be extended to real APIs in future).  
- Runs on a schedule or on-demand, ensuring the dashboard always shows updated data.

---

### 4. Database (AWS RDS)
- Stores **cost metrics** and **service status metrics** collected by the worker.  
- Backend queries the database to provide responses to the frontend.  
- Deployed in a **private subnet** for security.

---

## 🔄 Data Flow

1. **Worker** collects data from AWS/Azure/GCP and saves it into the database.  
2. **Backend** reads from the database and exposes REST APIs.  
3. **Frontend** calls the APIs and renders the metrics on the dashboard.  

---

## 📦 Learn More

- [Frontend (ReactJS)](../../frontend/README.md)  
- [Backend (Python APIs)](../../backend/README.md)  
- [Worker (Cloud Data Fetcher)](../../worker/README.md)  
- [Terraform (Infrastructure Setup)](../../terraform/README.md)  

---

## 📸 Preview

Main dashboard (cloud selector, cost metrics, server status):  
![Dashboard Screenshot](../../frontend/public/dashboard.png)

