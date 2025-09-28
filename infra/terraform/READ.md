# 🏗️ Terraform – Infrastructure as Code (IaC)

This module provisions and manages the **cloud infrastructure** required for the Multi-Cloud Dashboard.  
It ensures consistent, repeatable, and automated environment creation.

---

## 🎯 Role in the System

- Creates the **networking layer** (VPC, public/private subnets, security groups)  
- Deploys **compute resources** (EC2 instances, Docker runtime)  
- Sets up **database layer** (RDS instance)  
- Configures **application load balancer (ALB)** for frontend/backend containers  
- Enables **infrastructure teardown** when not needed  

---

## 📂 Key Modules

- **VPC** → Networking (VPC, subnets, route tables)  
- **Security** → Security groups and rules  
- **EC2** → Worker & container runtime hosts  
- **Database** → RDS setup (PostgreSQL/MySQL)  
- **ALB** → Application load balancer for blue-green deployments  

---

## 🔄 Workflows (GitHub Actions)

- **Infra Creation** → Runs Terraform `apply` to provision all resources  
- **Infra Destroy** → Runs Terraform `destroy` to clean up safely  
- **DevSecOps Integration** → SonarQube (code quality) & Trivy (vulnerability scan) are also triggered on Terraform workflows  

---

## 🛠️ Tech Stack

- **Terraform** – Infrastructure as Code  
- **AWS Provider** – VPC, EC2, RDS, ALB  
- **GitHub Actions** – Automated workflows (create/destroy + scans)  
