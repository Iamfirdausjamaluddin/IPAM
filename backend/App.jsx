import { useEffect, useState } from 'react'

function App() {
  const [ips, setIps] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('http://localhost:8000/ips')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json()
      })
      .then((data) => setIps(data))
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

      {!error && ips === null && (
        <p className="text-slate-600">Loading…</p>
      )}

      {ips && (
        <p className="text-slate-700">
          Loaded <span className="font-bold">{ips.length}</span> IPs from backend.
        </p>
      )}
    </div>
  )
}

export default App
