import { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const Dashboard = () => {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      navigate('/');
      return;
    }

    const fetchData = async () => {
      try {
        const response = await axios.get('http://localhost:5000/api/dashboard/lsp_summary', {
          headers: { Authorization: `Bearer ${token}` }
        });
        setData(response.data.data);
      } catch (err) {
        setError('Failed to fetch data');
      }
    };

    fetchData();
  }, [navigate]);

  const handleLogout = () => {
    localStorage.removeItem('token');
    navigate('/');
  };

  return (
    <div>
      <h2>Dashboard</h2>
      <button onClick={handleLogout}>Logout</button>
      {error && <p>{error}</p>}
      {data ? (
        <div>
          <h3>LSP Summary</h3>
          <p>Count: {data.count}</p>
          {Array.isArray(data.result) && data.result.length > 0 ? (
            <table border="1">
              <thead>
                <tr>
                  {Object.keys(data.result[0]).map(key => <th key={key}>{key}</th>)}
                </tr>
              </thead>
              <tbody>
                {data.result.map((row, i) => (
                  <tr key={i}>
                    {Object.keys(row).map(key => {
                      const val = row[key];

                      const formatValue = (k, v) => {
                        const normalizedKey = String(k).replace(/\s+/g, '').toLowerCase();
                        const isTotal = normalizedKey.includes('total') && normalizedKey.includes('amount');
                        if (isTotal) {
                          let num = NaN;
                          if (typeof v === 'number') num = v;
                          if (typeof v === 'string') num = parseFloat(v.replace(/,/g, ''));
                          return Number.isFinite(num) ? num.toFixed(2) : String(v ?? '');
                        }
                        return v == null ? '' : String(v);
                      };

                      const displayVal = formatValue(key, val);
                      return <td key={key}>{displayVal}</td>;
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p>No data available</p>
          )}
        </div>
      ) : (
        <p>Loading...</p>
      )}
    </div>
  );
};

export default Dashboard;