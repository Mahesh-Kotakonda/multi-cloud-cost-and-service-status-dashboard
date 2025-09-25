import React, { useEffect, useState } from "react";
import "./Azure.css";

function Azure() {
  const [cloudData, setCloudData] = useState({ vm: [], costs: [] });
  const [loading, setLoading] = useState(true);
  const [selectedRegion, setSelectedRegion] = useState("ALL");
  const [selectedMonth, setSelectedMonth] = useState("");

  useEffect(() => {
    async function fetchCloudData() {
      try {
        const vmRes = await fetch("/api/AZURE/status");
        const costRes = await fetch("/api/AZURE/costs");
        if (!vmRes.ok || !costRes.ok) throw new Error("Failed fetching Azure data");

        const vmData = await vmRes.json();
        const costData = await costRes.json();

        setCloudData({ vm: vmData, costs: costData });

        if (costData.length) {
          const sortedMonths = [...new Set(costData.map((c) => c.month_year))]
            .sort()
            .reverse();
          setSelectedMonth(sortedMonths[0]);
        }
        setLoading(false);
      } catch (err) {
        console.error(err);
        setLoading(false);
      }
    }
    fetchCloudData();
  }, []);

  if (loading) return <div className="loading">Loading Azure dashboard...</div>;

  // --- Derived data ---
  const vmFiltered =
    selectedRegion === "ALL"
      ? cloudData.vm.filter((i) => i.az === "TOTAL" || i.az === "ALL")
      : cloudData.vm.filter((i) => i.region === selectedRegion);

  const regions = [
    ...new Set(cloudData.vm.filter((i) => i.az === "TOTAL").map((i) => i.region)),
  ];

  const monthNames = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December",
  ];

  const months = [...new Set(cloudData.costs.map((c) => c.month_year))]
    .sort()
    .reverse();

  const costsFiltered = selectedMonth
    ? cloudData.costs.filter((c) => c.month_year === selectedMonth)
    : [];

  const totalRecord = costsFiltered.find((c) => c.service === "TOTAL");

  const formatMonthName = (monthYear) => {
    const [year, month] = monthYear.split("-");
    return `${monthNames[parseInt(month) - 1]} ${year}`;
  };

  const formatCurrency = (val) =>
    new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(val);

  const getVMSummary = (data) => {
    const total = data.find((d) => d.az === "TOTAL" || d.az === "ALL") || {};
    return selectedRegion === "ALL" ? (
      <>
        Across all regions:{" "}
        <span className="badge running">{total.running || 0}</span> running,{" "}
        <span className="badge stopped">{total.stopped || 0}</span> stopped, and{" "}
        <span className="badge terminated">{total.terminated || 0}</span> terminated
        VMs.
      </>
    ) : (
      <>
        Region <strong>{selectedRegion}</strong>:{" "}
        <span className="badge running">{total.running || 0}</span> running,{" "}
        <span className="badge stopped">{total.stopped || 0}</span> stopped, and{" "}
        <span className="badge terminated">{total.terminated || 0}</span> terminated
        VMs.
      </>
    );
  };

  // --- Region cards for ALL view ---
  const regionCards =
    selectedRegion === "ALL"
      ? cloudData.vm
          .filter((d) => d.az === "TOTAL")
          .map((d, idx) => (
            <div key={idx} className="vm-card region-card">
              <h4>{d.region}</h4>
              <div className="status-group">
                <span className="badge running">Running: {d.running}</span>
                <span className="badge stopped">Stopped: {d.stopped}</span>
                <span className="badge terminated">Terminated: {d.terminated}</span>
              </div>
            </div>
          ))
      : null;

  return (
    <div className="azure-dashboard">
      {/* Left: VM (Compute) */}
      <section className="split-panel vm-panel">
        <h2>Cloud Compute Overview</h2>
        <label>
          Region:
          <select
            value={selectedRegion}
            onChange={(e) => setSelectedRegion(e.target.value)}
          >
            <option value="ALL">All Regions</option>
            {regions.map((r, idx) => (
              <option key={idx} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>

        <p className="vm-summary">{getVMSummary(vmFiltered)}</p>

        {/* Region-level cards when ALL selected */}
        {selectedRegion === "ALL" && (
          <div className="vm-cards region-cards">
            {regionCards}
          </div>
        )}

        {/* AZ-level cards when a region is selected */}
        {selectedRegion !== "ALL" && (
          <div className="vm-cards">
            {vmFiltered
              .filter((d) => d.az !== "TOTAL" && d.az !== "ALL")
              .map((d, idx) => (
                <div key={idx} className="vm-card">
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
              <option key={idx} value={m}>
                {formatMonthName(m)}
              </option>
            ))}
          </select>
        </label>

        {totalRecord && (
          <div className="total-cost-card">
            <h3>Total Cost</h3>
            <p className="total-cost-amount">
              {formatCurrency(totalRecord.total_amount)}
            </p>
            <span className="total-cost-month">
              {formatMonthName(totalRecord.month_year)}
            </span>
          </div>
        )}

        <h4 className="breakdown-title">Service Breakdown</h4>
        <div className="service-cards">
          {costsFiltered
            .filter((c) => c.service !== "TOTAL" && c.total_amount > 0)
            .map((c, idx) => (
              <div key={idx} className="service-card">
                <h5>{c.service}</h5>
                <p className="cost-amount">{formatCurrency(c.total_amount)}</p>
              </div>
            ))}
        </div>
      </section>
    </div>
  );
}

export default Azure;

