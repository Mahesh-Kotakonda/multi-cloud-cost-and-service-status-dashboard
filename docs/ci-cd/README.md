# ⚙️ CI/CD + DevSecOps

This project uses **GitHub Actions workflows** for application and infrastructure automation, along with **DevSecOps tools** for code quality and security scanning.

---

## 🔄 Workflows

### 1. **App Build**
- Triggered on code changes.  
- Builds **frontend, backend, and worker** Docker images.  
- Pushes images to the container registry.  
- Runs **SonarQube** (code quality) and **Trivy** (image vulnerability scan).  

### 2. **App Deploy**
- Deploys the built containers to EC2.  
- **Frontend & Backend** → Blue-Green deployment (zero downtime).  
- **Worker** → Rolling deployment strategy.  

### 3. **App Rollback**
- Triggered manually if a deployment fails.  
- Reads **JSON configs from S3** to identify the last stable version.  
- Removes failing containers and restores the previous image/config.  

### 4. **Infra Creation**
- Provisions infrastructure with **Terraform**:
  - VPC, Subnets, Security Groups  
  - Application Load Balancer  
  - EC2 Instances (for containers)  
  - RDS Database (private subnet)  
- Runs **SonarQube** (Terraform IaC static analysis) and **Trivy** (Terraform module security scan).  

### 5. **Infra Destroy**
- Safely tears down all resources created by Terraform.  

---

## 🛡️ DevSecOps Integration

### 🔹 SonarQube
- Runs in both **App Build** and **Infra Creation** workflows.  
- Performs **static code analysis** on:
  - Application code (Python, ReactJS)  
  - Terraform IaC files  
- Detects bugs, code smells, maintainability issues, and IaC misconfigurations.  

### 🔹 Trivy
- Runs in both **App Build** and **Infra Creation** workflows.  
- Scans **Docker images** for vulnerabilities.  
- Scans **Terraform modules** for misconfigurations and known CVEs.  
- Ensures both application and infrastructure are secure before deployment.  
