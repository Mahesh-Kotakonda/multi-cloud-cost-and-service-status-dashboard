# ⚙️ Worker – Multi-Cloud Data Fetcher

The worker is responsible for **collecting cloud cost and server status metrics** from AWS, Azure, and GCP.  
It runs as an **independent container** and continuously updates the database used by the backend APIs.

---

## 🎯 Role in the System

- Connects to configured cloud accounts  
- Fetches cost + server status metrics  
- Stores results in the database  
- Ensures data is always up to date for the dashboard  

---

## 🌐 Cloud Provider Support

- **AWS** → Live dynamic integration (real data via AWS SDK)  
- **Azure** → Currently generates dummy metrics (random realistic values)  
- **GCP** → Currently generates dummy metrics (random realistic values)  

> Future versions will extend Azure and GCP to **full dynamic integrations**.

---

## 🔄 Data Flow

1. Worker runs scheduled jobs / continuous loop  
2. Connects to AWS / Azure / GCP APIs (or dummy generators)  
3. Transforms data into unified format  
4. Stores into database (RDS)  
5. Backend exposes via REST APIs → Frontend displays  

---

## 🛠️ Tech Stack

- **Python**  
- **AWS SDK (boto3)** for AWS integration   
- **Database Client** (AWS RDS)  


