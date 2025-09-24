import React from "react";
import "./Header.css";

function Header() {
  return (
    <header className="header-container">
      <div className="header-content">
        <h1 className="header-title">Multi-Cloud Monitoring Dashboard</h1>
        <p className="header-subtitle">
          This dashboard helps track <strong>virtual services</strong> and{" "}
          <strong>server status</strong> across AWS, GCP, and Azure. It also
          provides <strong>account cost details</strong> for the current month
          along with comparisons from the last two months, giving a clear view of
          usage and trends.
        </p>
      </div>
    </header>
  );
}

export default Header;
