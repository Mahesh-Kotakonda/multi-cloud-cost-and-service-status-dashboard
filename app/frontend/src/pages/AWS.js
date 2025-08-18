import React, { useEffect, useState } from "react";
import "./AWS.css";

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

        if (!ec2Res.ok || !costRes.ok) throw new Error("Failed fetching AWS data");

        const ec2Data = await ec2Res.json();
        const costData = await costRes.json();

        setCloudData({ ec2: ec2Data, costs: costData });
        setLoading(false);
      } catch (err) {
        console.error(err);
        setLoading(false);
      }
    }

    fetchCloudData();
  }, []);

  if (loading) return <div className="loading">Loading AWS dashboard...</div>;

  const ec2Filtered = selectedRegion === "ALL"
    ? cloudData.ec2.filter(i => i.az === "TOTAL")
    : cloudData.ec2.filter(i => i.region === selectedRegion);

  // Professional EC2 Summary
  const getEC2Summary = (data) => {
    if (!data.length) return "No EC2 instances found.";

    let running = 0, stopped = 0, terminated = 0;
    data.forEach(d => {
      if (d.running) running += d.running;
      if (d.stopped) stopped += d.stopped;
      if (d.terminated) terminated += d.terminated;
    });

    const runningText = running ? `${running} running` : "";
    const stoppedText = stopped ? `${stopped} stopped` : "";
    const terminatedText = terminated ? `${terminated} terminated` : "";

    const allStatuses = [runningText, stoppedText, terminatedText].filter(Boolean).join(", ");

    return `EC2 Instance Overview for ${selectedRegion === "ALL" ? "all regions" : selectedRegion}: ${allStatuses}. Below is the detailed breakdown by Availability Zone.`;
  };

  const months = [...new Set(cloudData.costs.map(c => c.month_year))];
  const costsFiltered = selectedMonth
    ? cloudData.costs.filter(c => c.month_year === selectedMonth)
    : cloudData.costs.filter(c => c.month_year === months[0]);

  return (
    <div className="aws-dashboard">
      {/* EC2 Dashboard */}
      <section className="section ec2-dashboard">
        <h1>Cloud Compute Overview</h1>
        <label>
          Filter by Region:
          <select value={selectedRegion} onChange={(e) => setSelectedRegion(e.target.value)}>
            <option value="ALL">All Regions</option>
            {cloudData.ec2
              .filter(i => i.region !== "ALL" && i.az === "TOTAL")
              .map((i, idx) => <option key={idx} value={i.region}>{i.region}</option>)}
          </select>
        </label>

        <p className="ec2-summary">{getEC2Summary(ec2Filtered)}</p>

        {selectedRegion !== "ALL" && (
          <div className="ec2-cards">
            {ec2Filtered.filter(d => d.az !== "TOTAL").map((d, idx) => (
              <div key={idx} className="ec2-card">
                <h3>{d.az}</h3>
                {d.running > 0 && <p className="status-running">Running: {d.running}</p>}
                {d.stopped > 0 && <p className="status-stopped">Stopped: {d.stopped}</p>}
                {d.terminated > 0 && <p className="status-terminated">Terminated: {d.terminated}</p>}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Cost Dashboard */}
      <section className="section cost-dashboard">
        <h1>Cloud Cost Overview</h1>
        <label>
          Select Month:
          <select value={selectedMonth} onChange={(e) => setSelectedMonth(e.target.value)}>
            {months.map((m, idx) => <option key={idx} value={m}>{m}</option>)}
          </select>
        </label>

        <div className="service-cards">
          {costsFiltered.filter(c => c.pct_of_total > 0).map((c, idx) => (
            <div key={idx} className="service-card">
              <h4>{c.service}</h4>
              <p>Month: {c.month_year}</p>
              <p>Cost: ${c.total_amount.toLocaleString()}</p>
              <p>Contribution: {c.pct_of_total.toFixed(2)}%</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export default AWS;
