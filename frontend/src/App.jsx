import React, { useState, useEffect } from 'react';
import { TrendingUp, Plus, X, AlertCircle, RefreshCw } from 'lucide-react';

// HARDCODED BACKEND URL - Change this to your backend URL
const API_URL = 'https://stock-monitor-backend-rlpp.onrender.com';

const StockMonitor = () => {
  const [stocks, setStocks] = useState([]);
  const [newSymbol, setNewSymbol] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [marketOpen, setMarketOpen] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [updating, setUpdating] = useState(false);

  useEffect(() => {
    fetchMarketStatus();
    fetchStocks();
    
    const interval = setInterval(() => {
      fetchMarketStatus();
      if (marketOpen) {
        fetchStocks();
      }
    }, 30000);

    return () => clearInterval(interval);
  }, [marketOpen]);

  const fetchMarketStatus = async () => {
    try {
      console.log('Fetching market status from:', `${API_URL}/api/market-status`);
      const res = await fetch(`${API_URL}/api/market-status`);
      const data = await res.json();
      console.log('Market status:', data);
      setMarketOpen(data.is_open);
    } catch (err) {
      console.error('Error fetching market status:', err);
    }
  };

  const fetchStocks = async () => {
    try {
      console.log('Fetching stocks from:', `${API_URL}/api/stocks`);
      const res = await fetch(`${API_URL}/api/stocks`);
      const data = await res.json();
      console.log('Stocks:', data);
      setStocks(data);
      setLastUpdate(new Date());
    } catch (err) {
      console.error('Error fetching stocks:', err);
    }
  };

  const addStock = async () => {
    if (!newSymbol.trim()) {
      setError('Please enter a stock symbol');
      return;
    }

    setLoading(true);
    setError('');

    try {
      console.log('Adding stock:', newSymbol);
      const res = await fetch(`${API_URL}/api/stocks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: newSymbol.toUpperCase() })
      });

      console.log('Response status:', res.status);

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || 'Failed to add stock');
      }

      const data = await res.json();
      console.log('Added stock:', data);
      setStocks([...stocks, data]);
      setNewSymbol('');
    } catch (err) {
      console.error('Error adding stock:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const removeStock = async (symbol) => {
    try {
      const res = await fetch(`${API_URL}/api/stocks/${symbol}`, { 
        method: 'DELETE' 
      });

      if (res.ok) {
        setStocks(stocks.filter(s => s.symbol !== symbol));
      }
    } catch (err) {
      console.error('Error removing stock:', err);
    }
  };

  const updateAllStocks = async () => {
    setUpdating(true);
    try {
      const res = await fetch(`${API_URL}/api/stocks/update-all`, {
        method: 'POST'
      });

      if (res.ok) {
        const data = await res.json();
        setStocks(data);
        setLastUpdate(new Date());
      }
    } catch (err) {
      console.error('Error updating stocks:', err);
    } finally {
      setUpdating(false);
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'RED': return 'bg-red-500';
      case 'GREEN': return 'bg-green-500';
      case 'AMBER': return 'bg-amber-500';
      default: return 'bg-gray-400';
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-3 mb-4">
            <TrendingUp className="w-10 h-10 text-blue-600" />
            <h1 className="text-4xl font-bold text-gray-900">Stock Live Monitor</h1>
          </div>
          <div className="flex items-center justify-center gap-4">
            <p className="text-gray-700">
              Market Status: <span className={`font-semibold ${marketOpen ? 'text-green-600' : 'text-red-600'}`}>
                {marketOpen ? 'OPEN' : 'CLOSED'}
              </span>
            </p>
            <button
              onClick={updateAllStocks}
              disabled={updating || !marketOpen}
              className="p-2 hover:bg-gray-200 rounded-lg transition-colors disabled:opacity-50"
              title="Refresh All Stocks"
            >
              <RefreshCw className={`w-5 h-5 text-gray-600 ${updating ? 'animate-spin' : ''}`} />
            </button>
          </div>
          {lastUpdate && (
            <p className="text-sm text-gray-500 mt-2">
              Last updated: {lastUpdate.toLocaleTimeString('en-IN')}
            </p>
          )}
        </div>

        <div className="bg-white rounded-xl shadow-md p-6 mb-6 border border-gray-200">
          <div className="flex gap-3">
            <input
              type="text"
              value={newSymbol}
              onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
              onKeyPress={(e) => e.key === 'Enter' && addStock()}
              placeholder="Enter stock symbol (e.g., ICICIBANK.NS, RELIANCE.NS)"
              className="flex-1 px-4 py-3 bg-white border border-gray-300 rounded-lg text-gray-900 placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
            />
            <button
              onClick={addStock}
              disabled={loading}
              className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white rounded-lg font-semibold flex items-center gap-2 transition-colors"
            >
              {loading ? (
                <>
                  <RefreshCw className="w-5 h-5 animate-spin" />
                  Adding...
                </>
              ) : (
                <>
                  <Plus className="w-5 h-5" />
                  Add Stock
                </>
              )}
            </button>
          </div>
          {error && (
            <div className="mt-3 flex items-center gap-2 text-red-600 bg-red-50 p-3 rounded-lg">
              <AlertCircle className="w-4 h-4" />
              <span>{error}</span>
            </div>
          )}
          <div className="mt-3 text-sm text-gray-600">
            <p><strong>Popular NSE Stocks:</strong> RELIANCE.NS, TCS.NS, HDFCBANK.NS, INFY.NS, ICICIBANK.NS</p>
          </div>
        </div>

        <div className="bg-white rounded-xl shadow-md border border-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-100">
                <tr>
                  <th className="px-6 py-4 text-left text-sm font-semibold text-gray-700">Symbol</th>
                  <th className="px-6 py-4 text-center text-sm font-semibold text-gray-700">Last Price</th>
                  <th className="px-6 py-4 text-center text-sm font-semibold text-gray-700">Current High</th>
                  <th className="px-6 py-4 text-center text-sm font-semibold text-gray-700">Current Low</th>
                  <th className="px-6 py-4 text-center text-sm font-semibold text-gray-700">10:30 High</th>
                  <th className="px-6 py-4 text-center text-sm font-semibold text-gray-700">10:30 Low</th>
                  <th className="px-6 py-4 text-center text-sm font-semibold text-gray-700">Status</th>
                  <th className="px-6 py-4 text-center text-sm font-semibold text-gray-700">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {stocks.length === 0 ? (
                  <tr>
                    <td colSpan="8" className="px-6 py-12 text-center text-gray-500">
                      No stocks added yet. Add a stock to start monitoring real-time prices.
                    </td>
                  </tr>
                ) : (
                  stocks.map((stock) => (
                    <tr key={stock.symbol} className="hover:bg-gray-50 transition-colors">
                      <td className="px-6 py-4 text-gray-900 font-semibold">{stock.symbol}</td>
                      <td className="px-6 py-4 text-center text-gray-900 font-medium">
                        {stock.lastPrice ? `₹${stock.lastPrice.toFixed(2)}` : '-'}
                      </td>
                      <td className="px-6 py-4 text-center text-green-600 font-medium">
                        {stock.currentHigh ? `₹${stock.currentHigh.toFixed(2)}` : '-'}
                      </td>
                      <td className="px-6 py-4 text-center text-red-600 font-medium">
                        {stock.currentLow ? `₹${stock.currentLow.toFixed(2)}` : '-'}
                      </td>
                      <td className="px-6 py-4 text-center text-blue-600 font-medium">
                        {stock.high1030 ? `₹${stock.high1030.toFixed(2)}` : '-'}
                      </td>
                      <td className="px-6 py-4 text-center text-orange-600 font-medium">
                        {stock.low1030 ? `₹${stock.low1030.toFixed(2)}` : '-'}
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center justify-center gap-2">
                          <div className={`w-3 h-3 rounded-full ${getStatusColor(stock.status)}`}></div>
                          <span className="text-gray-700 text-sm font-medium">{stock.status}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-center">
                        <button
                          onClick={() => removeStock(stock.symbol)}
                          className="text-red-600 hover:text-red-700 transition-colors p-1 hover:bg-red-50 rounded"
                        >
                          <X className="w-5 h-5" />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="mt-6 text-center text-gray-600 text-sm space-y-2">
          <p>🔄 Prices update automatically every 30 seconds during market hours (9:15 AM - 3:30 PM IST)</p>
          <p>📊 Data fetched from Yahoo Finance in real-time</p>
          <p>💾 All data is stored in PostgreSQL database</p>
        </div>
      </div>
    </div>
  );
};

export default StockMonitor;
