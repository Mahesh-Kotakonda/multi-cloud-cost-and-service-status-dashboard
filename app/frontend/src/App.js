import React, { useEffect, useState } from "react";

function App() {
  const [ec2Data, setEc2Data] = useState([]);
  const [costData, setCostData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        // ✅ Use relative URLs so they work via the same ALB
        const ec2Response = await fetch("/aws/ec2-status");
        if (!ec2Response.ok) throw new Error("Failed to fetch EC2 status");
        const ec2Json = await ec2Response.json();

        const costResponse = await fetch("/aws/costs");
        if (!costResponse.ok) throw new Error("Failed to fetch AWS costs");
        const costJson = await costResponse.json();

        setEc2Data(ec2Json);
        setCostData(costJson);
        setLoading(false);
      } catch (err) {
        console.error("Error fetching data:", err);
        setLoading(false);
      }
    }

    fetchData();
  }, []);

  if (loading) return <div>Loading...</div>;

  return (
    <div style={{ padding: "20px", fontFamily: "Arial" }}>
      <h1>AWS Dashboard</h1>

      <h2>EC2 Status</h2>
      <table border="1" cellPadding="5" cellSpacing="0">
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
          {ec2Data.map((item, idx) => (
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

      <h2>AWS Cost</h2>
      <pre>{JSON.stringify(costData, null, 2)}</pre>
    </div>
  );
}

export default App;
