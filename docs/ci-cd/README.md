# ⚙️ CI/CD + DevSecOps

This project uses **GitHub Actions workflows** for application and infrastructure automation, along with **DevSecOps tools** for code quality and security scanning.

---

## 🔄 Workflows

### 1. **App Build**
The application build workflow ensures that every code change is verified for quality and security **before deployment**.

**Steps in sequence:**
1. **SonarQube Scans** → frontend, backend, worker  
2. **Trivy FS Scans** → filesystem vulnerabilities in frontend, backend, worker  
3. **Trivy Config Scans** → IaC/config validation for frontend, backend, worker  
4. **Build Docker Images** → frontend, backend, worker  
5. **Trivy Image Scans** → security scan on built images  
6. **Push Images to Registry**  
7. **Trigger App Deployment** (only if all previous checks succeed)  

---

#### ✅ Positive Scenario
1. All **SonarQube scans** (frontend, backend, worker) pass.  
2. All **Trivy FS & Config scans** succeed.  
3. **Docker images** are built successfully.  
4. **Trivy image scans** pass for all images.  
5. Images are pushed to registry.  
6. **App Deployment** is triggered automatically.  

📸 Screenshot (Positive Scenario):  
![App Build Positive](./app-build-positive.png)

---

#### ❌ Negative Scenario
1. **Worker container** fails SonarQube scan → build for worker is skipped.  
2. **Frontend & backend** pass SonarQube + Trivy FS/Config → they proceed to build.  
3. During **Trivy image scan**, one of the images fails.  
4. As a result, the **image push job fails**.  
5. **App Deployment is not triggered**.  

📸 Screenshot (Negative Scenario):  
![App Build Negative](./app-build-negative.png)

---

### 2. **App Deploy**
- Deploys the built containers to **EC2 instances**.  
- **Frontend & Backend** → Blue-Green deployment (zero downtime).  
- **Worker** → Rolling deployment strategy.  

---

### 3. **App Rollback**
- Triggered manually if a deployment fails.  
- Uses **S3 JSON configs** to identify the last stable version.  
- Removes failing containers and restores the previous image/config.  

---

### 4. **Infra Creation**
This workflow provisions infrastructure securely with **Terraform** and validates its quality before applying.

**Steps in sequence:**
1. **SonarQube Scan** → static code analysis of Terraform project  
2. **Trivy FS Scan** → filesystem scan for Terraform modules  
3. **Trivy Config Scan** → IaC misconfiguration scan  
4. **Terraform Apply** → provisions VPC, subnets, ALB, EC2, RDS  

---

#### ✅ Positive Scenario
1. **SonarQube** scan for Terraform passes.  
2. **Trivy FS & Config scans** succeed.  
3. Terraform infrastructure resources are created successfully.  

📸 Screenshot (Positive Scenario):  
![Infra Creation Positive](./infra-positive.png)

---

#### ❌ Negative Scenario
1. **SonarQube scan** for Terraform fails → deployment blocked.  
2. Or, **Trivy FS/Config scan** finds misconfigurations.  
3. In either case, Terraform **does not proceed with apply**.  

📸 Screenshot (Negative Scenario):  
![Infra Creation Negative](./infra-negative.png)

---

### 5. **Infra Destroy**
- Safely tears down all resources created by Terraform.  
- No scans are executed in this workflow.  

---

## 🛡️ DevSecOps Integration

### 🔹 SonarQube
- Runs in both **App Build** and **Infra Creation** workflows.  
- Performs **static code analysis** on:
  - Application code (Python, ReactJS)  
  - Terraform IaC files  
- Detects **bugs, vulnerabilities, code smells, maintainability issues, and IaC misconfigurations**.  

### 🔹 Trivy
- Integrated into both workflows:  
  - **FS Scans** → filesystem-level vulnerabilities (apps + Terraform)  
  - **Config Scans** → detect IaC misconfigurations (apps + Terraform)  
  - **Image Scans** → container CVEs after Docker build  
- Ensures **end-to-end security** before deployment.  

---

## 📸 Scan Results

### 🔹 SonarQube Portal Overview
All four projects are tracked independently:  
- **Frontend Project**  
- **Backend Project**  
- **Worker Project**  
- **Terraform Project**  

📸 Screenshot:  
![SonarQube Projects](./sonar-projects.png)

---

### 🔹 SonarQube Project Dashboards
Detailed per-project analysis (bugs, vulnerabilities, code smells, new vs overall code):  

- **Frontend Project**  
  ![SonarQube Frontend](./sonar-frontend.png)  

- **Backend Project**  
  ![SonarQube Backend](./sonar-backend.png)  

- **Worker Project**  
  ![SonarQube Worker](./sonar-worker.png)  

- **Terraform Project**  
  ![SonarQube Terraform](./sonar-terraform.png)  

---

### 🔹 Trivy Scan Proofs

#### App Build
- **FS Scans** (frontend)  
  ![Trivy FS App](./frontend_trivy-fs-app.png)  

- **Config Scans** (frontend)  
  ![Trivy Config App](./frontend_trivy-config-app.png)  

- **Docker Image Scans** (frontend)  
  ![Trivy Image App](./frontend_trivy-image-app.png)
  
- **FS Scans** (backend)  
  ![Trivy FS App](./backend_trivy-fs-app.png)  

- **Config Scans** (backend)  
  ![Trivy Config App](./backend_trivy-config-app.png)  

- **Docker Image Scans** (backend)  
  ![Trivy Image App](./backend_trivy-image-app.png)
  
- **FS Scans** (worker)  
  ![Trivy FS App](./worker_trivy-fs-app.png)  

- **Config Scans** (worker)  
  ![Trivy Config App](./worker_trivy-config-app.png)  

- **Docker Image Scans** (worker)  
  ![Trivy Image App](./worker_trivy-image-app.png) 

#### Infra Creation
- **FS Scan (Terraform)**  
  ![Trivy FS Terraform](./trivy-fs-terraform.png)  

- **Config Scan (Terraform)**  
  ![Trivy Config Terraform](./trivy-config-terraform.png)  

---

## ✅ Summary
This CI/CD + DevSecOps setup ensures:  
- **Quality & Security Gates** at every stage  
- **Zero-downtime deployments** with Blue-Green + Rolling strategies  
- **Automated rollback** with S3 JSON configs  
- **Full traceability** with screenshots from SonarQube and Trivy scans  



