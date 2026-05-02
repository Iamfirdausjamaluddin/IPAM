import { useEffect, useState } from 'react'

function App() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('http://localhost:8000/ips')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json()
      })
      .then((json) => setData(json))
      .catch((err) => setError(err.message))
  }, [])

  return (
    <div className="min-h-screen bg-slate-100 p-8">
      <h1 className="text-3xl font-bold text-slate-800 mb-4">
        Homelab IPAM
      </h1>

      {error && (
        <p className="text-red-600">Error: {error}</p>
      )}

      {!error && data === null && (
        <p className="text-slate-600">Loading…</p>
      )}

      {data && (
        <p className="text-slate-700">
          Loaded <span className="font-bold">{data.count}</span> IPs from backend.
          {' '}
          <span className="text-slate-500 text-sm">
            ({data.ips.filter((ip) => ip.is_alive).length} alive)
          </span>
        </p>
      )}
    </div>
  )
}

export default App
