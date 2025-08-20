import React from "react";
import "./Header.css";

function Header() {
  return (
    <header className="header-container">
      <div className="header-content">
        <h1 className="header-title">Multi-Cloud Monitoring Dashboard</h1>
        <p className="header-subtitle">
          Real-time updates on cloud costs and service status across AWS, GCP, Azure.
        </p>

      </div>
    </header>
  );
}

export default Header;





