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

  // EC2 Summary Paragraph
  const getEC2Summary = (data) => {
    const total = data.find((d) => d.az === "TOTAL" || d.az === "ALL") || {};
    return selectedRegion === "ALL"
      ? `There are ${total.running || 0} running, ${total.stopped || 0} stopped, and ${total.terminated || 0} terminated instances across all regions.`
      : `Region ${selectedRegion} has ${total.running || 0} running, ${total.stopped || 0} stopped, and ${total.terminated || 0} terminated instances.`;
  };

  // Unique regions for dropdown
  const regions = cloudData.ec2.filter((i) => i.az === "TOTAL").map((i) => i.region);

  // Month dropdown
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
                  {d.running > 0 && <p className="status-running">Running: {d.running}</p>}
                  {d.stopped > 0 && <p className="status-stopped">Stopped: {d.stopped}</p>}
                  {d.terminated > 0 && <p className="status-terminated">Terminated: {d.terminated}</p>}
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

        <div className="service-cards">
          {costsFiltered.filter((c) => c.total_amount > 0).map((c, idx) => (
            <div key={idx} className="service-card">
              <h4>{c.service}</h4>
              <p>Month: {formatMonthName(c.month_year)}</p>
              <p className="cost-amount">${c.total_amount.toLocaleString()}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export default AWS;
