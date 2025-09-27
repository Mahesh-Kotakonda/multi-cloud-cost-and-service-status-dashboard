import React from "react";
import "./Header.css";

function Header() {
  return (
    <header className="header-container">
      <div className="header-content">
        <h1 className="header-title">Multi-Cloud Monitoring Dashboard</h1>
        <p className="header-subtitle">
          A single dashboard to track <strong>cloud servers</strong> 
          (like AWS EC2 or Azure VMs) and analyze <strong>account costs</strong> 
          for the <strong>current</strong> and <strong>last two months</strong> 
          across AWS, GCP, and Azure.
        </p>
      </div>
    </header>
  );
}

export default Header;
