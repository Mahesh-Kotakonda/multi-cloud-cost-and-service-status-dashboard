# 🌐 Multi-Cloud Cost & Service Status Dashboard

A **unified web dashboard** to monitor **AWS, Azure, and Google Cloud** accounts.  
The dashboard provides both **cost insights** and **service status** in a single view:  
- 💰 Cost metrics → Current month + previous two months  
- 🖥️ Server status → Region-wise and availability-zone-wise  

---

## ✨ Overview

Cloud environments often generate **unexpected bills** from unused or forgotten resources.  
Organizations with multiple accounts across AWS, Azure, and GCP lack a **centralized view** of both costs and service usage.  

This project addresses the problem by offering a **multi-cloud dashboard** where users can:  
- Select a cloud provider  
- View cost data (current month, previous months)  
- View server status by region and availability zone  

The solution also integrates **CI/CD automation, DevSecOps tools, and resilient deployment strategies** to reflect real-world cloud operations.

---

## 🏗️ Architecture Summary

The system is built with **containers, pipelines, and infrastructure automation**:

- **Pipelines**
  - **App Build** – Builds frontend, backend, and worker containers.  
  - **App Deploy** – Blue-green deployment for frontend/backend, rolling updates for worker.  
  - **App Rollback** – Safe rollback via S3-stored JSON configs.  
  - **Infra Create** – Provisions VPC, subnets, ALB, RDS, and EC2.  
  - **Infra Destroy** – Cleans up resources securely.  

- **Containers**
  - **Frontend (ReactJS)** – Web dashboard with cloud selector, cost view, and server status view.  
  - **Backend (Python)** – REST APIs to serve cost and server status metrics.  
  - **Worker (Python)** – Connects to cloud accounts, collects cost & service metrics, and stores them in the database.  

- **Deployment Strategies**
  - **Blue-Green (frontend/backend)** → Zero-downtime container switching.  
  - **Rolling (worker)** → Smooth updates without downtime.  
  - **Rollback** → Restores previous version via stored configs.  

---

## 🚀 Features

- ✅ **Multi-cloud monitoring** – AWS, Azure, GCP  
- ✅ **Cost metrics** – Current + last 2 months  
- ✅ **Server status** – Region-wise & availability-zone-wise  
- ✅ **REST APIs** – `/api/aws/costs`, `/api/aws/status`, etc.  
- ✅ **DevSecOps integration** – SonarQube (code quality), Trivy (vulnerability scanning)  
- ✅ **Automated rollback** – Previous deployment recovery with zero downtime  
- ✅ **Infrastructure automation** – Provision and teardown via Terraform  

---

## 🛠️ Tech Stack

- **Frontend:** ReactJS  
- **Backend:** Python (Flask/FastAPI)  
- **Worker:** Python (multi-cloud SDKs)  
- **Database:** AWS RDS (PostgreSQL/MySQL)  
- **Infrastructure:** Terraform (VPC, Subnets, ALB, EC2, RDS)  
- **CI/CD:** GitHub Actions (build, deploy, rollback, infra)  
- **Security:** SonarQube, Trivy  
- **Containers:** Docker  

---

## 📚 Documentation

- [Documentation Index](./docs/README.md)  
- [Application](./docs/application/README.md)  
- [Architecture](./docs/architecture/README.md)  
- [CI/CD + DevSecOps](./docs/ci-cd/README.md)  
- [Terraform](./docs/terraform/README.md)  

---

## 📸 Preview

Main dashboard view (cloud selector, cost & server status):  
![Dashboard Screenshot](./docs/application
/multi-cloud-and-service-status-dashboard.png
)
