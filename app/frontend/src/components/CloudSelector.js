import React from "react";
import "./CloudSelector.css";

function CloudSelector({ selectedCloud, setSelectedCloud }) {
  const clouds = [
    { id: "AWS", label: "Amazon Web Services (AWS)" },
    { id: "GCP", label: "Google Cloud Platform (GCP)" },
    { id: "Azure", label: "Microsoft Azure" },
  ];

  return (
    <div className="cloud-selector-wrapper">
    <p className="cloud-description">
      Choose a provider to track its <strong>server status </strong> 
      (e.g., AWS EC2, Azure VMs) and review <strong>account costs </strong> 
      for the <strong>current</strong> and <strong>last two months</strong>.
    </p>


      <div className="cloud-selector-container">
        <label htmlFor="cloud-select" className="cloud-label">
          Choose Cloud:
        </label>
        <select
          id="cloud-select"
          className="cloud-select"
          value={selectedCloud}
          onChange={(e) => setSelectedCloud(e.target.value)}
        >
          {clouds.map((cloud) => (
            <option key={cloud.id} value={cloud.id}>
              {cloud.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

export default CloudSelector;





