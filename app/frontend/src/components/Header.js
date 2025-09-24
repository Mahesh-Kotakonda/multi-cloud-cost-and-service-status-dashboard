import React from "react";
import "./Header.css";
import CloudSelector from "./CloudSelector";

function Header({ selectedCloud, setSelectedCloud }) {
  return (
    <header className="header-container">
      <div className="header-content">
        <div className="header-text">
          <h1 className="header-title">Multi-Cloud Monitoring Dashboard</h1>
          <p className="header-subtitle">
            This dashboard gives a single place to check the overall{" "}
            <strong>host status</strong> and <strong>server status</strong> across
            cloud providers. By selecting AWS, GCP, or Azure, you can quickly view
            the current health and cost details for that cloud account.
          </p>
        </div>

        <div className="header-selector">
          <CloudSelector
            selectedCloud={selectedCloud}
            setSelectedCloud={setSelectedCloud}
          />
        </div>
      </div>
    </header>
  );
}

export default Header;
