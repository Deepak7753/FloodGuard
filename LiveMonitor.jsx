import { useEffect, useState } from 'react'
import axios from 'axios'
import { API } from './api.js'

const POLL_MS = 5000

const STATUS = {
  NORMAL:  { label: 'Normal',  badge: 'bg-emerald-950 text-emerald-400 border-emerald-700', dot: 'bg-emerald-400', card: 'border-slate-800' },
  WATCH:   { label: 'Watch',   badge: 'bg-yellow-950 text-yellow-300 border-yellow-700',    dot: 'bg-yellow-300',  card: 'border-yellow-800' },
  WARNING: { label: 'Warning', badge: 'bg-orange-950 text-orange-400 border-orange-600',    dot: 'bg-orange-400',  card: 'border-orange-700' },
  DANGER:  { label: 'Danger',  badge: 'bg-red-950 text-red-400 border-red-600',             dot: 'bg-red-500 animate-pulse', card: 'border-red-600 shadow-lg shadow-red-950' },
  OFFLINE: { label: 'Offline', badge: 'bg-slate-900 text-slate-500 border-slate-700',       dot: 'bg-slate-600',   card: 'border-slate-800 opacity-70' },
  NO_DATA: { label: 'No data', badge: 'bg-slate-900 text-slate-500 border-slate-700',       dot: 'bg-slate-600',   card: 'border-slate-800 opacity-70' },
}
const ORDER = ['DANGER', 'WARNING', 'WATCH', 'NORMAL', 'OFFLINE', 'NO_DATA']

const ago = (s) => s == null ? '—' : s < 90 ? `${s}s ago` : s < 5400 ? `${Math.round(s / 60)} min ago` : `${(s / 3600).toFixed(1)} h ago`
const fmtTime = (ts) => new Date(ts * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })

function Badge({ status }) {
  const s = STATUS[status] || STATUS.NO_DATA
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded border text-xs font-semibold uppercase tracking-wider ${s.badge}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />{s.label}
    </span>
  )
}

function LevelChart({ readings, warn, danger }) {
  if (!readings || readings.length < 2) {
    return <p className="text-xs text-slate-600 py-10 text-center">Not enough history yet</p>
  }
  const W = 640, H = 200, padL = 46, padR = 12, padT = 12, padB = 24
  const t0 = readings[0].ts, t1 = readings[readings.length - 1].ts
  const lv = readings.map(r => r.water_level_m)
  const lo = Math.min(...lv, warn) - 0.3, hi = Math.max(...lv, danger) + 0.3
  const x = (t) => padL + ((t - t0) / Math.max(t1 - t0, 1)) * (W - padL - padR)
  const y = (v) => padT + (1 - (v - lo) / (hi - lo)) * (H - padT - padB)
  const path = readings.map((r, i) => `${i ? 'L' : 'M'}${x(r.ts).toFixed(1)},${y(r.water_level_m).toFixed(1)}`).join(' ')
  const last = readings[readings.length - 1]
  const line = (v, color, label) => (
    <g>
      <line x1={padL} x2={W - padR} y1={y(v)} y2={y(v)} stroke={color} strokeDasharray="5 4" strokeWidth="1" />
      <text x={W - padR} y={y(v) - 3} fill={color} fontSize="10" textAnchor="end">{label} {v.toFixed(2)} m</text>
    </g>
  )
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Water level over time">
      {[0, 0.5, 1].map(f => {
        const v = lo + f * (hi - lo)
        return <g key={f}>
          <line x1={padL} x2={W - padR} y1={y(v)} y2={y(v)} stroke="#1e293b" />
          <text x={padL - 6} y={y(v) + 3} fill="#64748b" fontSize="10" textAnchor="end">{v.toFixed(1)}</text>
        </g>
      })}
      {line(warn, '#fb923c', 'Warning')}
      {line(danger, '#ef4444', 'Danger')}
      <path d={path} fill="none" stroke="#38bdf8" strokeWidth="2" strokeLinejoin="round" />
      <circle cx={x(last.ts)} cy={y(last.water_level_m)} r="3.5" fill="#38bdf8" />
      <text x={padL} y={H - 6} fill="#64748b" fontSize="10">{fmtTime(t0)}</text>
      <text x={W - padR} y={H - 6} fill="#64748b" fontSize="10" textAnchor="end">{fmtTime(t1)}</text>
    </svg>
  )
}

function StationCard({ s, selected, onSelect }) {
  const st = STATUS[s.status] || STATUS.NO_DATA
  const l = s.latest
  const rate = l?.rate_m_hr
  return (
    <button onClick={onSelect}
      className={`text-left rounded-lg border bg-slate-900/40 p-4 transition-all hover:bg-slate-900/80 ${st.card} ${selected ? 'ring-1 ring-sky-500' : ''}`}>
      <div className="flex items-start justify-between gap-2 mb-3">
        <div>
          <p className="text-sm font-semibold text-slate-200">{s.name}</p>
          <p className="text-xs text-slate-600">{s.id} · {ago(s.age_s)}</p>
        </div>
        <Badge status={s.status} />
      </div>
      {l ? (
        <>
          <div className="flex items-end justify-between mb-2">
            <p className="text-2xl font-bold tabular-nums text-slate-100">{l.water_level_m.toFixed(2)}<span className="text-xs text-slate-500 ml-1">m</span></p>
            <p className={`text-xs tabular-nums ${rate >= 0.3 ? 'text-orange-400' : rate >= 0.15 ? 'text-yellow-300' : 'text-slate-500'}`}>
              {rate == null ? 'rate —' : `${rate >= 0 ? '▲' : '▼'} ${Math.abs(rate).toFixed(2)} m/h`}
            </p>
          </div>
          <div className="grid grid-cols-3 gap-2 text-xs text-slate-500">
            <span>🌧 {l.rain_mm_hr ?? '—'} mm/h</span>
            <span>💧 {l.soil_moisture_pct ?? '—'}%</span>
            <span className={l.battery_pct < 20 ? 'text-red-400' : ''}>🔋 {l.battery_pct ?? '—'}%</span>
          </div>
        </>
      ) : <p className="text-xs text-slate-600">Waiting for first reading…</p>}
    </button>
  )
}

export default function LiveMonitor() {
  const [stations, setStations] = useState([])
  const [alerts, setAlerts] = useState([])
  const [history, setHistory] = useState([])
  const [selId, setSelId] = useState(null)
  const [error, setError] = useState(null)
  const [updated, setUpdated] = useState(null)

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const [a, b] = await Promise.all([
          axios.get(`${API}/iot/stations`),
          axios.get(`${API}/iot/alerts`, { params: { limit: 15 } }),
        ])
        if (!alive) return
        const list = [...a.data.stations].sort((p, q) => ORDER.indexOf(p.status) - ORDER.indexOf(q.status) || p.id.localeCompare(q.id))
        setStations(list); setAlerts(b.data.alerts); setError(null); setUpdated(new Date())
        setSelId(cur => cur ?? list[0]?.id ?? null)
      } catch {
        if (alive) setError(`Cannot reach the API at ${API}`)
      }
    }
    load()
    const t = setInterval(load, POLL_MS)
    return () => { alive = false; clearInterval(t) }
  }, [])

  useEffect(() => {
    if (!selId) return
    let alive = true
    const load = () => axios.get(`${API}/iot/stations/${selId}/history`, { params: { hours: 8 } })
      .then(r => alive && setHistory(r.data.readings)).catch(() => {})
    load()
    const t = setInterval(load, POLL_MS)
    return () => { alive = false; clearInterval(t) }
  }, [selId])

  const sel = stations.find(s => s.id === selId)
  const counts = ORDER.reduce((o, k) => ({ ...o, [k]: stations.filter(s => s.status === k).length }), {})
  const names = Object.fromEntries(stations.map(s => [s.id, s.name]))

  return (
    <main className="max-w-6xl mx-auto px-6 py-8 space-y-6">
      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950/40 p-4 text-xs text-red-300">
          {error}. Start the backend with <code className="text-red-200">uvicorn main:app --port 8000</code>.
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        {['DANGER', 'WARNING', 'WATCH', 'NORMAL', 'OFFLINE'].map(k => (
          <div key={k} className="flex items-center gap-2 rounded border border-slate-800 bg-slate-900/40 px-3 py-1.5">
            <span className={`w-2 h-2 rounded-full ${STATUS[k].dot}`} />
            <span className="text-xs text-slate-500">{STATUS[k].label}</span>
            <span className="text-sm font-semibold text-slate-200 tabular-nums">{counts[k] || 0}</span>
          </div>
        ))}
        <span className="ml-auto text-xs text-slate-600">
          {updated ? `Updated ${updated.toLocaleTimeString()} · refreshes every ${POLL_MS / 1000}s` : 'Loading…'}
        </span>
      </div>

      {stations.length > 0 && stations.every(s => s.status === 'NO_DATA') && (
        <div className="rounded-lg border border-slate-800 bg-slate-900/30 p-4 text-xs text-slate-500">
          No sensor data yet. Run <code className="text-slate-300">python iot_simulator.py</code> to stream demo readings,
          or point an ESP32 node at <code className="text-slate-300">POST /iot/readings</code>.
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {stations.map(s => <StationCard key={s.id} s={s} selected={s.id === selId} onSelect={() => setSelId(s.id)} />)}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <section className="lg:col-span-3 rounded-lg border border-slate-800 bg-slate-900/30 p-4">
          <div className="flex items-center justify-between mb-3">
            <p className="text-xs text-slate-500 uppercase tracking-widest">Water level · last 8 h</p>
            {sel && <p className="text-xs text-slate-400">{sel.name}</p>}
          </div>
          {sel && <LevelChart readings={history} warn={sel.warning_level_m} danger={sel.danger_level_m} />}
          {sel?.reasons?.length > 0 && (
            <ul className="mt-3 space-y-1 border-t border-slate-800 pt-3">
              {sel.reasons.map((r, i) => <li key={i} className="text-xs text-slate-400">• {r}</li>)}
            </ul>
          )}
        </section>

        <section className="lg:col-span-2 rounded-lg border border-slate-800 bg-slate-900/30 p-4">
          <p className="text-xs text-slate-500 uppercase tracking-widest mb-3">Alert feed</p>
          {alerts.length === 0 ? <p className="text-xs text-slate-600">No alerts yet</p> : (
            <ul className="space-y-2 max-h-80 overflow-y-auto pr-1">
              {alerts.map(a => (
                <li key={a.id} className="rounded border border-slate-800 bg-slate-950/50 p-2.5">
                  <div className="flex items-center justify-between mb-1">
                    <Badge status={a.status} />
                    <span className="text-xs text-slate-600">{fmtTime(a.ts)}</span>
                  </div>
                  <p className="text-xs font-semibold text-slate-300">{names[a.station_id] || a.station_id}</p>
                  <p className="text-xs text-slate-500 leading-relaxed">{a.message.split('. ').slice(1).join('. ') || a.message}</p>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <p className="text-xs text-slate-700">
        Status comes from a rule engine (water level vs. station warning/danger levels, rate of rise, rainfall intensity).
        Demo stations use placeholder thresholds — configure official levels before real use.
      </p>
    </main>
  )
}
