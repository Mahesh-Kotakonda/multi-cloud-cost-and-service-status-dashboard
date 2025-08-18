import React from "react";

function CloudSelector({ selectedCloud, setSelectedCloud }) {
  return (
    <div style={{ margin: "20px 0", paddingLeft: "20px" }}>
      <label htmlFor="cloud-select" style={{ marginRight: "10px" }}>Select Cloud:</label>
      <select
        id="cloud-select"
        value={selectedCloud}
        onChange={(e) => setSelectedCloud(e.target.value)}
      >
        <option value="AWS">AWS</option>
        <option value="GCP">GCP (Coming Soon)</option>
        <option value="Azure">Azure (Coming Soon)</option>
      </select>
    </div>
  );
}

export default CloudSelector;
