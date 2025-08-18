import React, { useEffect, useState } from "react";

function AWS() {
  const [cloudData, setCloudData] = useState({});
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

  if (loading) return <div style={{ padding: 20 }}>Loading AWS dashboard...</div>;

  return (
    <div style={{ padding: "20px", fontFamily: "Arial, sans-serif" }}>
      <h2>AWS - Service Status</h2>
      <table border="1" cellPadding="5" cellSpacing="0" width="100%">
        <thead>
          <tr>
            <th>Region</th>
            <th>AZ</th>
            <th>Running</th>
            <th>Stopped</th>
            <th>Terminated</th>
            <th>Retrieved At</th>
          </tr>
        </thead>
        <tbody>
          {cloudData.ec2?.map((item, idx) => (
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

      <h2 style={{ marginTop: "20px" }}>AWS - Monthly Costs</h2>
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
          {cloudData.costs?.map((c, idx) => (
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
