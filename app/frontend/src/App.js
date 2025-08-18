import React, { useEffect, useState } from "react";

function App() {
  const [cloudData, setCloudData] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchCloudData() {
      try {
        // Future-proof: try fetching for all clouds
        const clouds = ["aws"]; // tomorrow backend may add "gcp", "azure"
        const results = {};

        for (const cloud of clouds) {
          const ec2Res = await fetch(`/api/${cloud}/status`);
          const costRes = await fetch(`/api/${cloud}/costs`);

          if (!ec2Res.ok || !costRes.ok) {
            throw new Error(`Failed fetching ${cloud} data`);
          }

          const ec2Data = await ec2Res.json();
          const costData = await costRes.json();

          results[cloud.toUpperCase()] = { ec2: ec2Data, costs: costData };
        }

        setCloudData(results);
        setLoading(false);
      } catch (err) {
        console.error("Error fetching cloud data:", err);
        setLoading(false);
      }
    }

    fetchCloudData();
  }, []);

  if (loading) return <div style={{ padding: 20 }}>Loading dashboard...</div>;

  return (
    <div style={{ padding: "20px", fontFamily: "Arial, sans-serif" }}>
      <h1>Multi-Cloud Cost & Status Dashboard</h1>

      {Object.entries(cloudData).map(([cloud, data]) => (
        <div key={cloud} style={{ marginBottom: "40px" }}>
          <h2>{cloud} - Service Status</h2>
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
              {data.ec2.map((item, idx) => (
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

          <h2 style={{ marginTop: "20px" }}>{cloud} - Monthly Costs</h2>
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
              {data.costs.map((c, idx) => (
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
      ))}
    </div>
  );
}

export default App;
