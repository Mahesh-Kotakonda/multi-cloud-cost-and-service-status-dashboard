import React from "react";
import "./Header.css"; // We'll create a separate CSS file

function Header() {
  return (
    <header className="header-container">
      <div className="header-content">
        <h1 className="header-title">Multi-Cloud Cost & Status Dashboard</h1>
        <p className="header-subtitle">
          Monitor your cloud costs and service status across AWS, GCP, Azure, and more.
        </p>
      </div>
    </header>
  );
}

export default Header;
