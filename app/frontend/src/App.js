import React, { useEffect, useState } from "react";

function App() {
  const [ec2Data, setEc2Data] = useState([]);
  const [costData, setCostData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        // Replace these URLs with your actual API endpoints
        const ec2Response = await fetch("http://localhost:5000/api/ec2-status");
        const ec2Json = await ec2Response.json();

        const costResponse = await fetch("http://localhost:5000/api/cost");
        const costJson = await costResponse.json();

        setEc2Data(ec2Json);
        setCostData(costJson);
        setLoading(false);
      } catch (err) {
        console.error("Error fetching data:", err);
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
