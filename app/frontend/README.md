# 🖥️ Frontend – Multi-Cloud Dashboard (ReactJS)

The frontend is the **interactive web interface** for the Multi-Cloud Cost & Service Status Dashboard.  
It allows users to select a cloud provider and instantly view **cost insights** and **server status** in a single screen.

---

## 📸 UI Preview

### 🌐 Main Dashboard
![Dashboard Screenshot](./public/dashboard.png)

- **Cloud Selector** → Switch between AWS, Azure, and GCP  
- **Cost Panel** → Current + last 2 months  
- **Server Status Panel** → Region & availability zone status  

*(More screenshots can be added for AWS/Azure/GCP views)*

---

## 🎯 How It Works

1. User selects a cloud provider from the header dropdown.  
2. The dashboard displays:  
   - 💰 **Cost metrics** (current month + previous 2 months)  
   - 🖥️ **Server status** (region & availability-zone level)  
3. Data is fetched from the backend via REST APIs:  
   - `/api/aws/costs`, `/api/aws/status`  
   - `/api/azure/costs`, `/api/azure/status`  
   - `/api/gcp/costs`, `/api/gcp/status`  

---

## 🛠️ Tech Stack

- **ReactJS** – UI framework  
- **Axios/Fetch** – API integration  
- **CSS Modules** – Styling  
