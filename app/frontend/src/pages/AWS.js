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
        setSelectedMonth(costData.length ? costData[0].month_year : "");
        setLoading(false);
      } catch (err) {
        console.error(err);
        setLoading(false);
      }
    }
    fetchCloudData();
  }, []);

  if (loading) return <div className="loading">Loading AWS dashboard...</div>;

  // Filter EC2 based on selected region
  const ec2Filtered = selectedRegion === "ALL"
    ? cloudData.ec2.filter(i => i.az === "TOTAL" || i.az === "ALL")
    : cloudData.ec2.filter(i => i.region === selectedRegion);

  // EC2 Summary Paragraph
  const getEC2Summary = (data) => {
    let running = 0, stopped = 0, terminated = 0;
    data.forEach(d => {
      running += d.running || 0;
      stopped += d.stopped || 0;
      terminated += d.terminated || 0;
    });
    return selectedRegion === "ALL"
      ? `There are ${running} running, ${stopped} stopped, and ${terminated} terminated instances in all regions. To view per-region details, please select a region.`
      : `Region ${selectedRegion} has ${running} running, ${stopped} stopped, and ${terminated} terminated instances. Below are details for availability zones in this region.`;
  };

  // Get months for cost dashboard
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
              .filter(i => i.az === "TOTAL")
              .map((i, idx) => <option key={idx} value={i.region}>{i.region}</option>)}
          </select>
        </label>

        <p className="ec2-summary">{getEC2Summary(ec2Filtered)}</p>

        {selectedRegion !== "ALL" && (
          <div className="ec2-cards">
            {ec2Filtered
              .filter(d => d.az !== "TOTAL" && d.az !== "ALL")
              .map((d, idx) => (
              <div key={idx} className="ec2-card">
                <h3>AZ: {d.az}</h3>
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
          {costsFiltered.filter(c => c.total_amount > 0).map((c, idx) => (
            <div key={idx} className="service-card">
              <h4>{c.service}</h4>
              <p>Month: {c.month_year}</p>
              <p>Cost: ${c.total_amount.toLocaleString()}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export default AWS;
