import React from "react";
import "./CloudSelector.css";

function CloudSelector({ selectedCloud, setSelectedCloud }) {
  return (
    <div className="cloud-selector-container">
      <label htmlFor="cloud-select" className="cloud-label">
        Select Cloud:
      </label>
      <select
        id="cloud-select"
        className="cloud-select"
        value={selectedCloud}
        onChange={(e) => setSelectedCloud(e.target.value)}
      >
        <option value="AWS">AWS</option>
        <option value="GCP" disabled>
          GCP (Coming Soon)
        </option>
        <option value="Azure" disabled>
          Azure (Coming Soon)
        </option>
      </select>
    </div>
  );
}

export default CloudSelector;
