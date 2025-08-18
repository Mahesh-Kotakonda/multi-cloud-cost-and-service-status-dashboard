import React, { useEffect, useState } from "react";
import "./AWS.css"; // import CSS

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

        // filter costs > 0% only for service cards
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

  if (loading) {
    return <div className="loading">Loading AWS dashboard...</div>;
  }

  const getStatusColor = (status) => {
    if (status === "Running") return "#4CAF50";
    if (status === "Stopped") return "#F44336";
    if (status === "Terminated") return "#9E9E9E";
    return "#000";
  };

  // Costs grouped by month
  const costsByMonth = {};
  cloudData.costs.forEach(c => {
    if (!costsByMonth[c.month_year]) costsByMonth[c.month_year] = [];
    costsByMonth[c.month_year].push(c);
  });

  const sortedMonths = Object.keys(costsByMonth).sort((a, b) => b.localeCompare(a)); // current month first

  return (
    <div className="aws-dashboard">
      {/* EC2 Dashboard */}
      <section className="section">
        <h1>AWS EC2 Dashboard</h1>
        <div className="ec2-cards">
          {cloudData.ec2.map((item, idx) => (
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
      <section className="section">
        <h1>AWS Costs Dashboard</h1>
        {sortedMonths.map(month => {
          const monthCosts = costsByMonth[month];
          const totalCostObj = monthCosts.find(c => c.service === "TOTAL");
          const totalCost = totalCostObj ? totalCostObj.total_amount : 0;

          const services = monthCosts.filter(c => c.service !== "TOTAL" && c.pct_of_total > 0);

          return (
            <div key={month} className="month-section">
              <h2>{month} Costs</h2>
              <div className="total-cost">
                Total Cost: ${totalCost.toFixed(2)}
              </div>
              <div className="service-cards">
                {services.map((c, idx) => (
                  <div key={idx} className="service-card">
                    <h4>{c.service}</h4>
                    <p>Amount: ${c.total_amount.toFixed(2)}</p>
                    <p>% of Total: {c.pct_of_total.toFixed(2)}%</p>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </section>
    </div>
  );
}

export default AWS;
