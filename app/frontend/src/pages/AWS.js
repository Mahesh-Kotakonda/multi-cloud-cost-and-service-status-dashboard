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
  const ec2Filtered =
    selectedRegion === "ALL"
      ? cloudData.ec2.filter((i) => i.az === "TOTAL" || i.az === "ALL")
      : cloudData.ec2.filter((i) => i.region === selectedRegion);

  const getEC2Summary = (data) => {
    const total = data.find((d) => d.az === "TOTAL" || d.az === "ALL") || {};
    return selectedRegion === "ALL"
      ? <>Across all regions: <span className="badge running">{total.running || 0}</span> running, <span className="badge stopped">{total.stopped || 0}</span> stopped, and <span className="badge terminated">{total.terminated || 0}</span> terminated instances.</>
      : <>Region <strong>{selectedRegion}</strong>: <span className="badge running">{total.running || 0}</span> running, <span className="badge stopped">{total.stopped || 0}</span> stopped, and <span className="badge terminated">{total.terminated || 0}</span> terminated instances.</>;
  };

  const regions = cloudData.ec2.filter((i) => i.az === "TOTAL").map((i) => i.region);

  const monthNames = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December"
  ];
  const months = [...new Set(cloudData.costs.map((c) => c.month_year))];

  const costsFiltered = selectedMonth
    ? cloudData.costs.filter((c) => c.month_year === selectedMonth)
    : cloudData.costs.filter((c) => c.month_year === months[0]);

  const formatMonthName = (monthYear) => {
    const [year, month] = monthYear.split("-");
    return `${monthNames[parseInt(month) - 1]} ${year}`;
  };

  return (
    <div className="aws-dashboard">
      {/* Left: EC2 */}
      <section className="split-panel ec2-panel">
        <h2>Cloud Compute Overview</h2>
        <label>
          Region:
          <select
            value={selectedRegion}
            onChange={(e) => setSelectedRegion(e.target.value)}
          >
            <option value="ALL">All Regions</option>
            {regions.map((r, idx) => (
              <option key={idx} value={r}>{r}</option>
            ))}
          </select>
        </label>

        <p className="ec2-summary">{getEC2Summary(ec2Filtered)}</p>

        {selectedRegion !== "ALL" && (
          <div className="ec2-cards">
            {ec2Filtered
              .filter((d) => d.az !== "TOTAL" && d.az !== "ALL")
              .map((d, idx) => (
                <div key={idx} className="ec2-card">
                  <h4>{d.az}</h4>
                  <div className="status-group">
                    <span className="badge running">Running: {d.running}</span>
                    <span className="badge stopped">Stopped: {d.stopped}</span>
                    <span className="badge terminated">Terminated: {d.terminated}</span>
                  </div>
                </div>
              ))}
          </div>
        )}
      </section>

      {/* Right: Cost */}
      <section className="split-panel cost-panel">
        <h2>Cloud Cost Overview</h2>
        <label>
          Month:
          <select
            value={selectedMonth}
            onChange={(e) => setSelectedMonth(e.target.value)}
          >
            {months.map((m, idx) => (
              <option key={idx} value={m}>{formatMonthName(m)}</option>
            ))}
          </select>
        </label>
      
        {/* Highlight total cost from backend (TOTAL record) */}
        {(() => {
          const totalRecord = costsFiltered.find((c) => c.service === "TOTAL");
          return (
            totalRecord && (
              <div className="total-cost-card">
                <h3>Total Cost</h3>
                <p className="total-cost-amount">${totalRecord.total_amount.toLocaleString()}</p>
                <span className="total-cost-month">{formatMonthName(totalRecord.month_year)}</span>
              </div>
            )
          );
        })()}
      
        {/* Breakdown by service */}
        <h4 className="breakdown-title">Service Breakdown</h4>
        <div className="service-cards">
          {costsFiltered
            .filter((c) => c.service !== "TOTAL" && c.total_amount > 0)
            .map((c, idx) => (
              <div key={idx} className="service-card">
                <h5>{c.service}</h5>
                <p className="cost-amount">${c.total_amount.toLocaleString()}</p>
              </div>
            ))}
        </div>
      </section>
    </div>
  );
}

export default AWS;
