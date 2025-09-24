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
        Select a cloud provider below to view its{" "}
        <strong>server status</strong> and <strong>account costs</strong>.
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
