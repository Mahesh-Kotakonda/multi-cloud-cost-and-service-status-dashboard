# ☁️ Terraform – Infrastructure as Code

The project infrastructure is fully automated using **Terraform**.  
It provisions a secure AWS environment for deploying the Multi-Cloud Dashboard and can be destroyed safely when not in use.

---

## 📂 Module Structure

The Terraform code is split into reusable modules:

- **VPC** → Creates VPC, public/private subnets, route tables, and internet/NAT gateways.  
- **Security** → Defines security groups (for ALB, EC2, RDS).  
- **ALB** → Provisions Application Load Balancer with listeners and target groups.  
- **EC2** → Launches EC2 instances for running containers.  
- **Database** → Creates RDS instance in private subnet.  

Each module has its own:
- `main.tf` → Resources  
- `variables.tf` → Input variables  
- `outputs.tf` → Outputs for dependency chaining  

---

## 🏗️ Main Config

At the root level:

- `main.tf` → Calls all modules  
- `variables.tf` → Global input variables  
- `outputs.tf` → Consolidated outputs  
- `terraform.tfvars` → Default values (can be overridden)  

---

## 🔄 Workflows with Terraform

Terraform execution is integrated into **GitHub Actions workflows**:

- **Infra Creation Workflow**
  - Runs `terraform init`, `terraform plan`, `terraform apply`  
  - Provisions VPC, subnets, ALB, EC2, RDS  
  - Runs **SonarQube** (IaC static analysis) and **Trivy** (IaC misconfiguration/vulnerability scan)  

- **Infra Destroy Workflow**
  - Runs `terraform destroy`  
  - Cleans up all provisioned resources safely  

---

## ⚡ Deployment Flow

1. Run **Infra Creation workflow** → Sets up infra.  
2. Run **App Build workflow** → Builds images + runs scans.  
3. Run **App Deploy workflow** → Deploys frontend, backend, worker containers on EC2.  

---

## 🛡️ Security & Best Practices

- **RDS in private subnet** → not exposed to the internet.  
- **ALB in public subnet** → manages incoming traffic securely.  
- **Least-privilege security groups** → restrict access between components.  
- **Terraform + DevSecOps scans** → ensures compliance before provisioning.  
