import React, { useEffect, useState } from "react";

function AWS() {
  const [cloudData, setCloudData] = useState({ ec2: [], costs: [] });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchCloudData() {
      try {
        const ec2Res = await fetch("/api/aws/status");
        const costRes = await fetch("/api/aws/costs");

        if (!ec2Res.ok || !costRes.ok) {
          throw new Error("Failed fetching AWS data");
        }

        const ec2Data = await ec2Res.json();
        const costData = await costRes.json();

        const filteredCosts = costData.filter(c => c.pct_of_total > 0);

        setCloudData({ ec2: ec2Data, costs: filteredCosts });
        setLoading(false);
      } catch (err) {
        console.error("Error fetching AWS data:", err);
        setLoading(false);
      }
    }

    fetchCloudData();
  }, []);

  if (loading) {
    return <div style={{ padding: 20, fontSize: 18 }}>Loading AWS dashboard...</div>;
  }

  // Aggregate EC2 data
  const aggregatedEC2 = {
    totalRunning: 0,
    totalStopped: 0,
    totalTerminated: 0,
    regions: []
  };

  cloudData.ec2.forEach(item => {
    aggregatedEC2.totalRunning += item.running;
    aggregatedEC2.totalStopped += item.stopped;
    aggregatedEC2.totalTerminated += item.terminated;
    aggregatedEC2.regions.push(item);
  });

  // Aggregate Costs
  const totalCost = cloudData.costs.reduce((acc, c) => acc + c.total_amount, 0);

  // Badge colors
  const getStatusColor = (status) => {
    if (status === "Running") return "#4CAF50"; // green
    if (status === "Stopped") return "#F44336"; // red
    if (status === "Terminated") return "#9E9E9E"; // gray
    return "#000";
  };

  return (
    <div style={{ padding: 20, fontFamily: "Arial, sans-serif", maxWidth: 900, margin: "0 auto" }}>
      <h1>AWS Dashboard</h1>

      {/* -------------------------------
          EC2 Summary Cards
      ------------------------------- */}
      <h2>EC2 Instances Overview</h2>
      <p>
        The total EC2 instances in your AWS account are shown below, 
        along with the breakdown per region. Status is indicated by color badges.
      </p>

      <div style={{ display: "flex", gap: "20px", marginBottom: "20px" }}>
        <div style={{ flex: 1, padding: "20px", background: "#f0f8ff", borderRadius: 8, textAlign: "center" }}>
          <h3>Total Running</h3>
          <span style={{ fontSize: 24, color: getStatusColor("Running") }}>{aggregatedEC2.totalRunning}</span>
        </div>
        <div style={{ flex: 1, padding: "20px", background: "#fff0f0", borderRadius: 8, textAlign: "center" }}>
          <h3>Total Stopped</h3>
          <span style={{ fontSize: 24, color: getStatusColor("Stopped") }}>{aggregatedEC2.totalStopped}</span>
        </div>
        <div style={{ flex: 1, padding: "20px", background: "#f5f5f5", borderRadius: 8, textAlign: "center" }}>
          <h3>Total Terminated</h3>
          <span style={{ fontSize: 24, color: getStatusColor("Terminated") }}>{aggregatedEC2.totalTerminated}</span>
        </div>
      </div>

      <h3>Regional Breakdown</h3>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "15px" }}>
        {aggregatedEC2.regions.map((item, idx) => (
          <div key={idx} style={{ flex: "1 1 200px", padding: 15, border: "1px solid #ddd", borderRadius: 8 }}>
            <h4>{item.region} - {item.az}</h4>
            <p><strong>Running:</strong> <span style={{ color: getStatusColor("Running") }}>{item.running}</span></p>
            <p><strong>Stopped:</strong> <span style={{ color: getStatusColor("Stopped") }}>{item.stopped}</span></p>
            <p><strong>Terminated:</strong> <span style={{ color: getStatusColor("Terminated") }}>{item.terminated}</span></p>
            <p style={{ fontSize: 12, color: "#666" }}>Retrieved: {item.retrieved_at}</p>
          </div>
        ))}
      </div>

      {/* -------------------------------
          Costs Section
      ------------------------------- */}
      <h2 style={{ marginTop: 40 }}>AWS Monthly Costs</h2>
      <p>
        The total cost across all services is shown below, along with per-service breakdowns. 
        Only services with cost greater than 0% of total are displayed.
      </p>

      <div style={{ display: "flex", gap: "20px", marginBottom: "20px" }}>
        <div style={{ flex: 1, padding: "20px", background: "#fffbe6", borderRadius: 8, textAlign: "center" }}>
          <h3>Total Cost</h3>
          <span style={{ fontSize: 24, color: "#FFA500" }}>${totalCost.toFixed(2)}</span>
        </div>
      </div>

      <h3>Per-Service Costs</h3>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "15px" }}>
        {cloudData.costs.map((c, idx) => (
          <div key={idx} style={{ flex: "1 1 250px", padding: 15, border: "1px solid #ddd", borderRadius: 8 }}>
            <h4>{c.service}</h4>
            <p><strong>Month:</strong> {c.month_year}</p>
            <p><strong>Amount:</strong> ${c.total_amount.toFixed(2)}</p>
            <p><strong>% of Total:</strong> {c.pct_of_total.toFixed(2)}%</p>
            <p style={{ fontSize: 12, color: "#666" }}>Retrieved: {c.retrieved_at}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default AWS;
