import React from "react";
import "./Header.css";

function Header() {
  return (
    <header className="header-container">
      <div className="header-content">
        <h1 className="header-title">Multi-Cloud Monitoring Dashboard</h1>
        <p className="header-subtitle">
          A single dashboard to <strong>monitor cloud servers</strong> 
          (AWS EC2, Azure VMs, GCP Compute Engine) and 
          <strong>analyze monthly account costs</strong>. 
          Compare usage and spending across providers 
          for the <strong>current</strong> and <strong>last two months</strong>.
        </p>

      </div>
    </header>
  );
}

export default Header;

