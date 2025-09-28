# 🏗️ Architecture

The **Multi-Cloud Cost & Service Status Dashboard** is designed as a containerized system, deployed on AWS with full infrastructure automation and CI/CD pipelines.

---

## ⚡ System Components

### 🔹 Infrastructure (via Terraform)
- **VPC** with public + private subnets  
- **Elastic Load Balancer (ALB)** for traffic distribution  
- **EC2 instances** (public subnets) hosting containers  
- **RDS Database** (private subnets) for storing cost & status metrics  
- **Security groups** to control access  

---

### 🔹 Containers
- **Frontend (ReactJS)** → Dashboard UI  
- **Backend (Python APIs)** → Provides REST endpoints  
- **Worker (Python)** → Collects metrics from multi-cloud accounts  

---

### 🔹 Pipelines
- **App Build** – Builds frontend, backend, worker containers.  
- **App Deploy** –  
  - Blue-Green deployment for frontend/backend.  
  - Rolling updates for worker.  
- **App Rollback** – Restores previous deployment using JSON configs stored in S3.  
- **Infra Create** – Provisions VPC, ALB, RDS, and EC2.  
- **Infra Destroy** – Safely cleans up resources.  

---

## 🔄 Deployment Strategies

- **Blue-Green (Frontend & Backend)**  
  - Two container versions (Blue & Green) run in parallel.  
  - ALB routes traffic only to the active version.  
  - Enables **zero downtime releases**.

- **Rolling (Worker)**  
  - Updates worker containers gradually.  
  - Ensures continuous data collection without interruptions.  

- **Rollback**  
  - Previous configs/images stored in S3.  
  - If a deployment fails, inactive containers are removed and replaced with the last stable version.  

