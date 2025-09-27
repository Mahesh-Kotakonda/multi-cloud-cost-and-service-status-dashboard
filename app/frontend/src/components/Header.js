import React from "react";
import "./Header.css";

function Header() {
  return (
    <header className="header-container">
      <div className="header-content">
        <h1 className="header-title">Multi-Cloud Monitoring Dashboard</h1>
        <p className="header-subtitle">
          Monitor <strong>server status</strong> and view{" "}
          <strong>account cost details</strong> for the current month across AWS,
          GCP, and AZURE — ALL in one place.
        </p>
      </div>
    </header>
  );
}

export default Header;


