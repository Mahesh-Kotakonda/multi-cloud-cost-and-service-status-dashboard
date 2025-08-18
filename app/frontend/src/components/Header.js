import React from "react";
import "./Header.css";

function Header() {
  return (
    <header className="header-container">
      <div className="header-content">
        <h1 className="header-title">Multi-Cloud Monitoring Dashboard</h1>
        <p className="header-subtitle">
          Real-time insights into your cloud infrastructure across AWS, GCP, Azure, and more.
          Track service statuses, monitor resource usage, view cost metrics, and optimize cloud performance—all in one centralized platform.
        </p>
      </div>
    </header>
  );
}

export default Header;
