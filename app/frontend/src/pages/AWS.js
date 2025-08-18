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

        // Filter cost entries with percentage > 0
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
    return <div style={{ padding: 20 }}>Loading AWS dashboard...</div>;
  }

  // -------------------------------
  // EC2 Data Aggregation
  // -------------------------------
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
    aggregatedEC2.regions.push(item); // Keep regional breakdown
  });

  // -------------------------------
  // Cost Data Aggregation
  // -------------------------------
  const totalCost = cloudData.costs.reduce((acc, c) => acc + c.total_amount, 0);

  return (
    <div style={{ padding: "20px", fontFamily: "Arial, sans-serif" }}>
      {/* -------------------------------
          EC2 Instances Section
          ------------------------------- */}
      <h2>AWS EC2 Instances Dashboard</h2>
      <p>
        This section shows the current status of all EC2 instances across all AWS regions. 
        The first row displays the total count for the entire account, followed by 
        detailed per-region breakdowns.
      </p>

      <table border="1" cellPadding="5" cellSpacing="0" width="100%">
        <thead>
          <tr>
            <th>Region</th>
            <th>Availability Zone (AZ)</th>
            <th>Running</th>
            <th>Stopped</th>
            <th>Terminated</th>
            <th>Retrieved At</th>
          </tr>
        </thead>
        <tbody>
          {/* Total row */}
          <tr style={{ fontWeight: 'bold', backgroundColor: '#f0f0f0' }}>
            <td>Total</td>
            <td>-</td>
            <td>{aggregatedEC2.totalRunning}</td>
            <td>{aggregatedEC2.totalStopped}</td>
            <td>{aggregatedEC2.totalTerminated}</td>
            <td>-</td>
          </tr>
          {/* Per-region rows */}
          {aggregatedEC2.regions.map((item, idx) => (
            <tr key={idx}>
              <td>{item.region}</td>
              <td>{item.az}</td>
              <td>{item.running}</td>
              <td>{item.stopped}</td>
              <td>{item.terminated}</td>
              <td>{item.retrieved_at}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* -------------------------------
          AWS Costs Section
          ------------------------------- */}
      <h2 style={{ marginTop: "40px" }}>AWS Monthly Costs</h2>
      <p>
        This section shows the monthly costs for each AWS service. 
        The first row shows the total cost across all services, followed by 
        per-service breakdowns. Only services with costs greater than 0% of the total are shown.
      </p>

      <table border="1" cellPadding="5" cellSpacing="0" width="100%">
        <thead>
          <tr>
            <th>Month</th>
            <th>Service</th>
            <th>Total ($)</th>
            <th>% of Total</th>
            <th>Retrieved At</th>
          </tr>
        </thead>
        <tbody>
          {/* Total row */}
          <tr style={{ fontWeight: 'bold', backgroundColor: '#f0f0f0' }}>
            <td>-</td>
            <td>Total</td>
            <td>{totalCost.toFixed(2)}</td>
            <td>100%</td>
            <td>-</td>
          </tr>
          {/* Per-service rows */}
          {cloudData.costs.map((c, idx) => (
            <tr key={idx}>
              <td>{c.month_year}</td>
              <td>{c.service}</td>
              <td>{c.total_amount.toFixed(2)}</td>
              <td>{c.pct_of_total.toFixed(2)}%</td>
              <td>{c.retrieved_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default AWS;
