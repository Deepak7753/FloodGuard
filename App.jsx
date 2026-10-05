import { useEffect, useState } from 'react'
import axios from 'axios'
import { API } from './api.js'
import LiveMonitor from './LiveMonitor.jsx'
import Predictor from './Predictor.jsx'

const TABS = [
  { id: 'monitor', label: '📡 Live Monitor' },
  { id: 'predict', label: '🧠 Severity Predictor' },
]

function useApiHealth() {
  const [ok, setOk] = useState(null)
  useEffect(() => {
    let alive = true
    const ping = () => axios.get(`${API}/health`, { timeout: 4000 })
      .then(() => alive && setOk(true)).catch(() => alive && setOk(false))
    ping()
    const t = setInterval(ping, 15000)
    return () => { alive = false; clearInterval(t) }
  }, [])
  return ok
}

export default function App() {
  const [tab, setTab] = useState('monitor')
  const ok = useApiHealth()

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200" style={{ fontFamily: "'IBM Plex Mono',monospace" }}>
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-6 py-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🌊</span>
            <div>
              <h1 className="text-lg font-semibold tracking-tight text-slate-100">FloodGuard</h1>
              <p className="text-xs text-slate-500">AI/IoT Flood Early-Warning System</p>
            </div>
          </div>
          <nav className="flex gap-1" aria-label="Views">
            {TABS.map(t => (
              <button key={t.id} onClick={() => setTab(t.id)}
                className={`px-3 py-1.5 text-xs rounded border transition-all ${
                  tab === t.id ? 'border-sky-500 text-sky-300 bg-slate-800' : 'border-slate-800 text-slate-500 hover:text-slate-300 hover:border-slate-600'}`}>
                {t.label}
              </button>
            ))}
          </nav>
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span className={`w-2 h-2 rounded-full ${ok === null ? 'bg-slate-600' : ok ? 'bg-emerald-400 animate-pulse' : 'bg-red-500'}`} />
            {ok === null ? 'Checking API…' : ok ? 'API connected' : 'API offline'}
          </div>
        </div>
      </header>

      {tab === 'monitor' ? <LiveMonitor /> : <Predictor />}
    </div>
  )
}
