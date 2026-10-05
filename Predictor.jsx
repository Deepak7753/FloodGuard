import { useState } from 'react'
import axios from 'axios'
import { API } from './api.js'
const DEMOS = {
  high: {
    label: 'High Risk', emoji: '🔴',
    data: {
      rainfall_1d: 95, rainfall_3d: 210, rainfall_5d: 310, rainfall_7d: 370, rainfall_10d: 420,
      peak_discharge: 12000, flood_volume: '',
      event_duration: 4, time_to_peak: 1, recession_time: 3,
      peak_flood_level: 28.5, num_peaks: 2, start_month: 8,
      drainage_area: 18000, catchment_relief: 1800, drainage_density: 0.00018,
      ruggedness_number: 0.32, stream_order: 6, form_factor: 0.29,
      sinuosity_index: 1.55, elongation_ratio: 1.8e-10, infiltration_number: 2.5e-12,
      annual_mean_temp: 26, annual_precipitation: 2100,
      precip_wettest_month: 620, precip_seasonality: 135,
      population_density: 850, urban_percentage: 28,
      road_density: 420, hdi_2015: 0.58, night_light: 4.2,
      land_cover: 'Cropland', soil_type: 'Vertisols',
      koppen_climate: 'Tropical', lithology: 'Unconsolidated sediments',
    }
  },
  moderate: {
    label: 'Moderate', emoji: '🟡',
    data: {
      rainfall_1d: 30, rainfall_3d: 110, rainfall_5d: 200, rainfall_7d: 270, rainfall_10d: 329,
      peak_discharge: '', flood_volume: '',
      event_duration: 3, time_to_peak: 2, recession_time: 2,
      peak_flood_level: 9.0, num_peaks: 1, start_month: 8,
      drainage_area: 21904, catchment_relief: 1204, drainage_density: 0.000162,
      ruggedness_number: 0.195, stream_order: 5, form_factor: 0.188,
      sinuosity_index: 1.404, elongation_ratio: 7.02e-11, infiltration_number: 2.95e-12,
      annual_mean_temp: 25.3, annual_precipitation: 1214,
      precip_wettest_month: 306, precip_seasonality: 116,
      population_density: 723, urban_percentage: 42.3,
      road_density: 433, hdi_2015: 0.547, night_light: 7.76,
      land_cover: 'Cropland', soil_type: 'Luvisols',
      koppen_climate: 'Tropical', lithology: 'Metamorphics',
    }
  },
  low: {
    label: 'Low Risk', emoji: '🟢',
    data: {
      rainfall_1d: 5, rainfall_3d: 12, rainfall_5d: 18, rainfall_7d: 22, rainfall_10d: 25,
      peak_discharge: 180, flood_volume: '',
      event_duration: 2, time_to_peak: 1, recession_time: 1,
      peak_flood_level: 4.2, num_peaks: 1, start_month: 3,
      drainage_area: 320, catchment_relief: 280, drainage_density: 0.00012,
      ruggedness_number: 0.04, stream_order: 2, form_factor: 0.55,
      sinuosity_index: 1.12, elongation_ratio: 6e-11, infiltration_number: 2.2e-12,
      annual_mean_temp: 29, annual_precipitation: 620,
      precip_wettest_month: 95, precip_seasonality: 88,
      population_density: 45, urban_percentage: 2,
      road_density: 80, hdi_2015: 0.51, night_light: 0.3,
      land_cover: 'No dominant class', soil_type: 'Leptosols',
      koppen_climate: 'Arid', lithology: 'Metamorphics',
    }
  }
}

const EMPTY = Object.fromEntries(Object.keys(DEMOS.high.data).map(k => [k, '']))

const SECTIONS = [
  { title: 'Precipitation', icon: '🌧', fields: [
    { key: 'rainfall_1d',  label: '1-day rainfall',  unit: 'mm' },
    { key: 'rainfall_3d',  label: '3-day rainfall',  unit: 'mm' },
    { key: 'rainfall_5d',  label: '5-day rainfall',  unit: 'mm' },
    { key: 'rainfall_7d',  label: '7-day rainfall',  unit: 'mm', optional: true },
    { key: 'rainfall_10d', label: '10-day rainfall', unit: 'mm' },
  ]},
  { title: 'Flood Event', icon: '🌊', fields: [
    { key: 'peak_discharge',   label: 'Peak discharge',   unit: 'cumec', optional: true },
    { key: 'flood_volume',     label: 'Flood volume',     unit: 'cumec', optional: true },
    { key: 'event_duration',   label: 'Duration',         unit: 'days'  },
    { key: 'time_to_peak',     label: 'Time to peak',     unit: 'days'  },
    { key: 'recession_time',   label: 'Recession time',   unit: 'days'  },
    { key: 'peak_flood_level', label: 'Peak flood level', unit: 'm'     },
    { key: 'num_peaks',        label: 'Num peaks',        unit: 'count' },
    { key: 'start_month',      label: 'Start month',      unit: '1–12'  },
  ]},
  { title: 'Catchment', icon: '⛰', fields: [
    { key: 'drainage_area',       label: 'Drainage area',    unit: 'km²'  },
    { key: 'catchment_relief',    label: 'Relief',           unit: 'm'    },
    { key: 'drainage_density',    label: 'Drain density',    unit: ''     },
    { key: 'ruggedness_number',   label: 'Ruggedness',       unit: ''     },
    { key: 'stream_order',        label: 'Stream order',     unit: ''     },
    { key: 'form_factor',         label: 'Form factor',      unit: ''     },
    { key: 'sinuosity_index',     label: 'Sinuosity',        unit: ''     },
    { key: 'elongation_ratio',    label: 'Elongation ratio', unit: ''     },
    { key: 'infiltration_number', label: 'Infiltration no.', unit: ''     },
  ]},
  { title: 'Climate & Society', icon: '🌍', fields: [
    { key: 'annual_mean_temp',     label: 'Mean temp',          unit: '°C'     },
    { key: 'annual_precipitation', label: 'Annual precip',      unit: 'mm'     },
    { key: 'precip_wettest_month', label: 'Wettest month',      unit: 'mm'     },
    { key: 'precip_seasonality',   label: 'Precip seasonality', unit: 'CV'     },
    { key: 'population_density',   label: 'Population density', unit: '/km²'   },
    { key: 'urban_percentage',     label: 'Urban %',            unit: '%'      },
    { key: 'road_density',         label: 'Road density',       unit: 'km/km²' },
    { key: 'hdi_2015',             label: 'HDI 2015',           unit: '0–1'    },
    { key: 'night_light',          label: 'Night light',        unit: ''       },
  ]},
  { title: 'Classification', icon: '🗂', fields: [
    { key: 'land_cover',    label: 'Land cover',     type: 'select', options: ['Cropland','Forest','Mosaic vegetation','No dominant class'] },
    { key: 'soil_type',     label: 'Soil type',      type: 'select', options: ['Acrisols','Cambisols','Fluvisols','Leptosols','Lixisols','Luvisols','No dominant class','Vertisols'] },
    { key: 'koppen_climate',label: 'Köppen climate', type: 'select', options: ['Arid','No dominant class','Temperate','Tropical'] },
    { key: 'lithology',     label: 'Lithology',      type: 'select', options: ['Acid plutonic rocks','Basic volcanic rocks','Metamorphics','No dominant class','Siliciclastic sedimentary rocks','Unconsolidated sediments'] },
  ]},
]

const RISK = {
  High:     { bg:'bg-red-950',     border:'border-red-500',     text:'text-red-400',     bar:'bg-red-500',     shadow:'shadow-red-900'     },
  Moderate: { bg:'bg-amber-950',   border:'border-amber-400',   text:'text-amber-400',   bar:'bg-amber-400',   shadow:'shadow-amber-900'   },
  Low:      { bg:'bg-emerald-950', border:'border-emerald-500', text:'text-emerald-400', bar:'bg-emerald-500', shadow:'shadow-emerald-900' },
}

export default function Predictor() {
  const [form, setForm]       = useState(EMPTY)
  const [result, setResult]   = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)
  const [activeDemo, setActiveDemo] = useState(null)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const loadDemo = (key) => {
    setForm(Object.fromEntries(Object.entries(DEMOS[key].data).map(([k,v]) => [k, v === '' ? '' : String(v)])))
    setActiveDemo(key)
    setResult(null)
    setError(null)
  }

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true); setError(null); setResult(null)
    const payload = {}
    for (const [k, v] of Object.entries(form)) {
      if (v === '' || v === null || v === undefined) {
        payload[k] = null
        continue
      }
      const n = Number(v)
      payload[k] = isNaN(n) ? v : n
    }
    try {
      const { data } = await axios.post(`${API}/predict`, payload)
      setResult(data)
    } catch (err) {
      const d = err.response?.data?.detail
      setError(
        !err.response ? `Cannot reach the API at ${API}. Is the backend running?`
        : typeof d === 'string' ? d
        : Array.isArray(d) ? d.map(x => `${(x.loc || []).slice(1).join('.')}: ${x.msg}`).join('\n')
        : JSON.stringify(d, null, 2)
      )
    } finally { setLoading(false) }
  }

  const rc = result ? RISK[result.risk_label] : null
  const pct = result ? Math.round(result.risk_score * 100) : 0

  return (
    <div>

      <main className="max-w-6xl mx-auto px-6 py-8 grid grid-cols-1 lg:grid-cols-5 gap-8">

        <div className="lg:col-span-3 space-y-5">

          <div>
            <p className="text-xs text-slate-500 uppercase tracking-widest mb-2">Load demo scenario</p>
            <div className="flex flex-wrap gap-2">
              {Object.entries(DEMOS).map(([k, d]) => (
                <button key={k} onClick={() => loadDemo(k)}
                  className={`px-3 py-1.5 text-xs rounded border transition-all duration-200 ${
                    activeDemo === k ? 'border-slate-400 text-slate-200 bg-slate-800'
                                    : 'border-slate-700 text-slate-500 hover:border-slate-500 hover:text-slate-300'
                  }`}>
                  {d.emoji} {d.label}
                </button>
              ))}
              <button onClick={() => {setForm(EMPTY);setActiveDemo(null);setResult(null);setError(null)}}
                className="px-3 py-1.5 text-xs rounded border border-slate-800 text-slate-600 hover:text-slate-400 hover:border-slate-600 transition-all">
                ✕ Clear
              </button>
            </div>
          </div>

          <form onSubmit={submit} className="space-y-4">
            {SECTIONS.map(section => (
              <div key={section.title} className="rounded-lg border border-slate-800 bg-slate-900/40 overflow-hidden">
                <div className="px-4 py-2.5 bg-slate-800/50 border-b border-slate-800 flex items-center gap-2">
                  <span className="text-sm">{section.icon}</span>
                  <span className="text-xs font-semibold tracking-widest text-slate-400 uppercase">{section.title}</span>
                </div>
                <div className="p-4 grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {section.fields.map(f => (
                    <div key={f.key}>
                      <label className="block text-xs text-slate-500 mb-1">
                        {f.label}
                        {f.unit ? <span className="text-slate-700 ml-1">({f.unit})</span> : null}
                        {f.optional ? <span className="text-slate-700 ml-1 italic">opt</span> : null}
                      </label>
                      {f.type === 'select' ? (
                        <select value={form[f.key]} onChange={e => set(f.key, e.target.value)} required
                          className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-slate-500 transition-colors">
                          <option value="">— select —</option>
                          {f.options.map(o => <option key={o} value={o}>{o}</option>)}
                        </select>
                      ) : (
                        <input type="number" step="any" value={form[f.key]}
                          onChange={e => set(f.key, e.target.value)}
                          required={!f.optional} placeholder="—"
                          className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 placeholder-slate-700 focus:outline-none focus:border-slate-500 transition-colors"/>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}

            <button type="submit" disabled={loading}
              className="w-full py-3 rounded-lg border border-slate-600 bg-slate-800 hover:bg-slate-700 text-sm font-semibold tracking-widest uppercase text-slate-200 disabled:opacity-40 transition-all duration-200 hover:border-slate-400">
              {loading ? '⟳  Running model…' : '▶  Predict Flood Severity'}
            </button>
          </form>
        </div>

        <div className="lg:col-span-2">
          <div className="sticky top-24 space-y-4">

            <p className="text-xs text-slate-500 border border-slate-800 rounded-lg p-3 leading-relaxed">
              Rates the <b className="text-slate-400">severity of an observed flood event</b> from its recorded
              hydrology and catchment data. It is not a forecast — use the Live Monitor for real-time warnings.
            </p>

            {result ? (
              <div className={`rounded-xl border-2 ${rc.border} ${rc.bg} p-6 transition-all duration-300 shadow-xl ${rc.shadow}`}>
                <div className="flex items-start justify-between mb-5">
                  <div>
                    <p className="text-xs text-slate-500 uppercase tracking-widest mb-1">Severity</p>
                    <p className={`text-3xl font-bold ${rc.text}`}>{result.risk_label}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-slate-500 uppercase tracking-widest mb-1">Score</p>
                    <p className={`text-4xl font-bold tabular-nums ${rc.text}`}>{pct}%</p>
                  </div>
                </div>

                <div className="mb-5">
                  <div className="h-2 rounded-full bg-slate-800 overflow-hidden">
                    <div className={`h-full rounded-full ${rc.bar} transition-all duration-700`} style={{width:`${pct}%`}}/>
                  </div>
                  <div className="flex justify-between text-xs text-slate-600 mt-1">
                    <span>0%</span><span>Low · Moderate · High</span><span>100%</span>
                  </div>
                </div>

                <div className="rounded bg-slate-900/60 px-3 py-2 mb-4">
                  <p className="text-xs text-slate-500 uppercase tracking-wider mb-1">Confidence</p>
                  <p className="text-xs text-slate-300">{result.confidence}</p>
                </div>

                <div className="grid grid-cols-3 gap-2 text-center mb-4">
                  {[['High','≥65%','text-red-400'],['Moderate','35–65%','text-amber-400'],['Low','<35%','text-emerald-400']].map(([l,r,c])=>(
                    <div key={l} className="bg-slate-900/60 rounded px-2 py-1.5">
                      <p className={`text-xs font-bold ${c}`}>{l}</p>
                      <p className="text-xs text-slate-600">{r}</p>
                    </div>
                  ))}
                </div>

                <p className="text-xs text-slate-600 border-t border-slate-800 pt-3 leading-relaxed">{result.model_notes}</p>
              </div>
            ) : (
              <div className="rounded-xl border border-slate-800 bg-slate-900/30 p-10 text-center">
                <div className="text-4xl mb-3 opacity-20">🌊</div>
                <p className="text-xs text-slate-600">Load a demo or fill the form,<br/>then click Predict</p>
              </div>
            )}

            {error && (
              <div className="rounded-lg border border-red-800 bg-red-950/40 p-4">
                <p className="text-xs text-red-400 font-semibold mb-1">API Error</p>
                <pre className="text-xs text-red-300 whitespace-pre-wrap break-all">{error}</pre>
              </div>
            )}

            <div className="rounded-lg border border-slate-800 bg-slate-900/30 p-4">
              <p className="text-xs text-slate-600 uppercase tracking-widest mb-3">Model</p>
              <div className="space-y-1.5">
                {[['Algorithm','XGBoost'],['Training events','4,548'],['Gauges','155 CWC stations'],['Features','41 (37 num + 4 cat)'],['ROC-AUC','0.973'],['5-Fold CV AUC','0.968 ± 0.005'],['Source','INDOFLOODS · IIT Delhi 2025']].map(([k,v])=>(
                  <div key={k} className="flex justify-between text-xs">
                    <span className="text-slate-600">{k}</span>
                    <span className="text-slate-400 font-medium">{v}</span>
                  </div>
                ))}
              </div>
            </div>

          </div>
        </div>
      </main>
    </div>
  )
}
