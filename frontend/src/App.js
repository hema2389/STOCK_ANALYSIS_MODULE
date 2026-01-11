import { useEffect, useState } from "react";

const API = "https://YOUR-RENDER-BACKEND.onrender.com/api";

function App() {
  const [stocks, setStocks] = useState([]);
  const [symbol, setSymbol] = useState("");

  const loadStocks = async () => {
    const res = await fetch(`${API}/stocks`);
    setStocks(await res.json());
  };

  const updateAll = async () => {
    await fetch(`${API}/stocks/update-all`, { method: "POST" });
    loadStocks();
  };

  const addStock = async () => {
    if (!symbol) return;
    await fetch(`${API}/stocks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol }),
    });
    setSymbol("");
    loadStocks();
  };

  const deleteStock = async (sym) => {
    await fetch(`${API}/stocks/${sym}`, { method: "DELETE" });
    loadStocks();
  };

  useEffect(() => {
    loadStocks();
    const id = setInterval(() => {
      updateAll();
    }, 30000);
    return () => clearInterval(id);
  }, []);

  return (
    <div style={{ padding: 20 }}>
      <h1>📈 Stock Live Monitor</h1>

      <input
        value={symbol}
        onChange={(e) => setSymbol(e.target.value)}
        placeholder="ICICIBANK.NS"
      />
      <button onClick={addStock}>Add</button>

      <table border="1" cellPadding="8" style={{ marginTop: 20 }}>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Price</th>
            <th>High</th>
            <th>Low</th>
            <th>10:30 High</th>
            <th>10:30 Low</th>
            <th>Status</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {stocks.map((s) => (
            <tr key={s.id}>
              <td>{s.symbol}</td>
              <td>{s.lastPrice}</td>
              <td>{s.currentHigh}</td>
              <td>{s.currentLow}</td>
              <td>{s.high1030 ?? "-"}</td>
              <td>{s.low1030 ?? "-"}</td>
              <td>{s.status}</td>
              <td>
                <button onClick={() => deleteStock(s.symbol)}>❌</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default App;
