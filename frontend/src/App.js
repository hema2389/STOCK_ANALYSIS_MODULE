import { useEffect, useState } from "react";
import { TrendingUp } from "lucide-react";

const API = "https://YOUR-BACKEND.onrender.com/api";

export default function App() {
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
    const id = setInterval(updateAll, 30000);
    return () => clearInterval(id);
  }, []);

  const badge = (status) => {
    const map = {
      GREEN: "bg-green-100 text-green-700",
      RED: "bg-red-100 text-red-700",
      AMBER: "bg-yellow-100 text-yellow-700",
      NEUTRAL: "bg-gray-100 text-gray-700",
    };
    return (
      <span className={`px-2 py-1 rounded text-xs ${map[status]}`}>
        {status}
      </span>
    );
  };

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-6xl mx-auto bg-white rounded-xl shadow p-6">
        <h1 className="text-2xl font-bold flex items-center gap-2 mb-6">
          <TrendingUp className="text-blue-600" />
          Stock Live Monitor
        </h1>

        <div className="flex gap-2 mb-6">
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            placeholder="ICICIBANK.NS"
            className="border px-3 py-2 rounded w-60"
          />
          <button
            onClick={addStock}
            className="bg-blue-600 text-white px-4 py-2 rounded"
          >
            Add
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm border">
            <thead className="bg-gray-100">
              <tr>
                <th className="p-2 border">Symbol</th>
                <th className="p-2 border">Price</th>
                <th className="p-2 border">High</th>
                <th className="p-2 border">Low</th>
                <th className="p-2 border">10:30 High</th>
                <th className="p-2 border">10:30 Low</th>
                <th className="p-2 border">Status</th>
                <th className="p-2 border">Action</th>
              </tr>
            </thead>
            <tbody>
              {stocks.map((s) => (
                <tr key={s.id} className="text-center">
                  <td className="p-2 border font-semibold">{s.symbol}</td>
                  <td className="p-2 border">{s.lastPrice}</td>
                  <td className="p-2 border">{s.currentHigh}</td>
                  <td className="p-2 border">{s.currentLow}</td>
                  <td className="p-2 border">{s.high1030 ?? "-"}</td>
                  <td className="p-2 border">{s.low1030 ?? "-"}</td>
                  <td className="p-2 border">{badge(s.status)}</td>
                  <td className="p-2 border">
                    <button
                      onClick={() => deleteStock(s.symbol)}
                      className="text-red-600"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
              {!stocks.length && (
                <tr>
                  <td colSpan="8" className="p-4 text-gray-500">
                    No stocks added yet
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
