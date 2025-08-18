import React, { useEffect, useState } from "react";
import "./AWS.css";

function AWS() {
  const [cloudData, setCloudData] = useState({ ec2: [], costs: [] });
  const [loading, setLoading] = useState(true);
  const [selectedRegion, setSelectedRegion] = useState("ALL");
  const [selectedMonth, setSelectedMonth] = useState("2025-08");

  useEffect(() => {
    async function fetchCloudData() {
      try {
        const ec2Res = await fetch("/api/aws/status");
        const costRes = await fetch("/api/aws/costs");

        if (!ec2Res.ok || !costRes.ok) throw new Error("Failed fetching AWS data");

        const ec2Data = await ec2Res.json();
        const costData = await costRes.json();

        const filteredCosts = costData.filter(
          (c) => c.pct_of_total > 0 || c.service === "TOTAL"
        );

        setCloudData({ ec2: ec2Data, costs: filteredCosts });
        setLoading(false);
      } catch (err) {
        console.error("Error fetching AWS data:", err);
        setLoading(false);
      }
    }

    fetchCloudData();
  }, []);

  if (loading) return <div className="loading">Loading AWS dashboard...</div>;

  const getStatusColor = (status) => {
    if (status === "Running") return "#4CAF50";
    if (status === "Stopped") return "#F44336";
    if (status === "Terminated") return "#9E9E9E";
    return "#000";
  };

  const totalInstances = cloudData.ec2.find((e) => e.region === "ALL");

  const regions = Array.from(new Set(cloudData.ec2.map((e) => e.region))).filter(
    (r) => r !== "ALL"
  );

  const filteredEC2 =
    selectedRegion === "ALL"
      ? cloudData.ec2
      : cloudData.ec2.filter((e) => e.region === selectedRegion);

  const months = Array.from(new Set(cloudData.costs.map((c) => c.month_year)));
  const filteredCosts = cloudData.costs.filter((c) => c.month_year === selectedMonth);

  return (
    <div className="aws-dashboard" style={{ display: "flex", gap: "20px" }}>
      {/* EC2 Dashboard */}
      <section className="section" style={{ flex: 1 }}>
        <h1>AWS EC2 Dashboard</h1>
        <h2>Total Instances: {totalInstances ? totalInstances.running : 0}</h2>
        <label>
          Filter by Region:
          <select
            value={selectedRegion}
            onChange={(e) => setSelectedRegion(e.target.value)}
          >
            <option value="ALL">ALL</option>
            {regions.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
        <div className="ec2-cards">
          {filteredEC2.map((item, idx) => (
            <div key={idx} className="ec2-card">
              <h3>{item.region} - {item.az}</h3>
              <p>Running: <span style={{ color: getStatusColor("Running") }}>{item.running}</span></p>
              <p>Stopped: <span style={{ color: getStatusColor("Stopped") }}>{item.stopped}</span></p>
              <p>Terminated: <span style={{ color: getStatusColor("Terminated") }}>{item.terminated}</span></p>
            </div>
          ))}
        </div>
      </section>

      {/* Costs Dashboard */}
      <section className="section" style={{ flex: 1 }}>
        <h1>AWS Costs Dashboard</h1>
        <label>
          Select Month:
          <select
            value={selectedMonth}
            onChange={(e) => setSelectedMonth(e.target.value)}
          >
            {months.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </label>

        <div className="month-section">
          {filteredCosts.length > 0 && (
            <>
              <div className="total-cost">
                Total Cost: ${filteredCosts.find(c => c.service === "TOTAL")?.total_amount.toFixed(2) || 0}
              </div>
              <div className="service-cards">
                {filteredCosts
                  .filter(c => c.service !== "TOTAL")
                  .map((c, idx) => (
                    <div key={idx} className="service-card">
                      <h4>{c.service}</h4>
                      <p>Amount: ${c.total_amount.toFixed(2)}</p>
                      <p>% of Total: {c.pct_of_total.toFixed(2)}%</p>
                    </div>
                  ))}
              </div>
            </>
          )}
        </div>
      </section>
    </div>
  );
}

export default AWS;
