import React, { useEffect, useState } from "react";

const API_BASE = process.env.REACT_APP_API_BASE || "";

export default function App() {
  const [metrics, setMetrics] = useState([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    try {
      const res = await fetch(`${API_BASE}/metrics`);
      const data = await res.json();
      setMetrics(data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, []);

  return (
    <div style={{ padding: 16, fontFamily: "system-ui, Arial" }}>
      <h1>Resource Metrics</h1>
      {loading ? (
        <p>Loading...</p>
      ) : (
        <table border="1" cellPadding="6" cellSpacing="0">
          <thead>
            <tr>
              <th>ID</th>
              <th>Resource</th>
              <th>CPU %</th>
              <th>Memory %</th>
              <th>Status</th>
              <th>Time (UTC)</th>
            </tr>
          </thead>
          <tbody>
            {metrics.map((m) => (
              <tr key={m.id}>
                <td>{m.id}</td>
                <td>{m.resource_name}</td>
                <td>{m.cpu_usage}</td>
                <td>{m.memory_usage}</td>
                <td>{m.status}</td>
                <td>{new Date(m.created_at).toISOString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
