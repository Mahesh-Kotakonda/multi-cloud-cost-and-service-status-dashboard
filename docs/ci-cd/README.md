# ⚙️ CI/CD + DevSecOps

This project uses **GitHub Actions workflows** for application and infrastructure automation, along with **DevSecOps tools** for code quality and security scanning.

---

## 🔄 Workflows

### 1. **App Build**
- Triggered on code changes.  
- Runs **SonarQube** (static code analysis) and **Trivy FS/config scans** (IaC & filesystem vulnerabilities).  
- Builds **frontend, backend, and worker** Docker images.  
- Runs a **3rd security scan on built Docker images (Trivy)**.  
- If all scans pass → pushes images to the container registry and triggers **App Deployment**.  

#### ✅ Positive Scenario
1. **SonarQube** scans (frontend, backend, worker) pass.  
2. **Trivy FS & config scans** succeed.  
3. **Docker images** for frontend, backend, worker are built.  
4. **Trivy Docker image scans** pass.  
5. Images are **pushed to registry**.  
6. **App Deployment** is triggered automatically.  

📸 Screenshot (Positive Scenario):  
![App Build Positive](./app-build-positive.png)

#### ❌ Negative Scenario
1. **Worker container** fails SonarQube scan (skipped from build).  
2. **Frontend & backend** pass SonarQube + Trivy FS/config scans → their builds succeed.  
3. **Docker image scan (3rd scan)** fails for one of the built images.  
4. As a result, the **image publish step fails**.  
5. **App Deployment is not triggered**.  

📸 Screenshot (Negative Scenario):  
![App Build Negative](./app-build-negative.png)

---

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
- **FS & Config Scans** → Check filesystem and IaC misconfigurations.  
- **Docker Image Scans** → Run after image build to detect CVEs inside container images.  
- Ensures both application and infrastructure are secure before deployment.  

