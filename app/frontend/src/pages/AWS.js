import React, { useEffect, useState } from "react";
import "./AWS.css"; // import updated CSS

function AWS() {
  const [cloudData, setCloudData] = useState({ ec2: [], costs: [] });
  const [loading, setLoading] = useState(true);
  const [selectedRegion, setSelectedRegion] = useState("ALL");
  const [selectedMonth, setSelectedMonth] = useState("");

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

        const filteredCosts = costData.filter(c => c.pct_of_total > 0 || c.service === "TOTAL");

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

  // Filtered EC2 based on region
  const ec2Filtered = selectedRegion === "ALL"
    ? cloudData.ec2.filter(i => i.az === "ALL")
    : cloudData.ec2.filter(i => i.region === selectedRegion && i.az === "TOTAL");

  const getEC2Summary = (data) => {
    if (!data || data.length === 0) return "No instances are currently running.";
    const running = data.reduce((acc, cur) => acc + cur.running, 0);
    const stopped = data.reduce((acc, cur) => acc + cur.stopped, 0);
    const terminated = data.reduce((acc, cur) => acc + cur.terminated, 0);

    let summary = `Currently, there are ${running} instance${running !== 1 ? "s" : ""} running`;
    if (stopped) summary += `, ${stopped} instance${stopped !== 1 ? "s" : ""} are stopped`;
    if (terminated) summary += `, and ${terminated} instance${terminated !== 1 ? "s" : ""} have been terminated.`;

    summary += " The infrastructure is stable and monitored as per operational guidelines.";

    return summary;
  };

  // Cost filtering by month
  const months = [...new Set(cloudData.costs.map(c => c.month_year))];
  const costsFiltered = selectedMonth
    ? cloudData.costs.filter(c => c.month_year === selectedMonth)
    : cloudData.costs.filter(c => c.month_year === months[0]);

  return (
    <div className="aws-dashboard">
      <div className="dashboard-container">
        {/* EC2 Dashboard */}
        <section className="section ec2-dashboard">
          <h1>Cloud Compute Overview</h1>

          <label>
            Filter by Region: 
            <select value={selectedRegion} onChange={(e) => setSelectedRegion(e.target.value)}>
              <option value="ALL">All Regions</option>
              {cloudData.ec2.map((i, idx) => i.region !== "ALL" && i.az === "TOTAL" ? (
                <option key={idx} value={i.region}>{i.region}</option>
              ) : null)}
            </select>
          </label>

          <p className="ec2-summary">{getEC2Summary(ec2Filtered)}</p>
        </section>

        {/* Cost Dashboard */}
        <section className="section cost-dashboard">
          <h1>Cloud Cost Overview</h1>

          <label>
            Select Month: 
            <select value={selectedMonth} onChange={(e) => setSelectedMonth(e.target.value)}>
              {months.map((m, idx) => (
                <option key={idx} value={m}>{m}</option>
              ))}
            </select>
          </label>

          <div className="service-cards">
            {costsFiltered.filter(c => c.service !== "TOTAL" && c.pct_of_total > 0).map((c, idx) => (
              <div key={idx} className="service-card">
                <h4>{c.service}</h4>
                <p>Cost: ${c.total_amount.toFixed(2)}</p>
                <p>Contribution: {c.pct_of_total.toFixed(2)}%</p>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

export default AWS;
