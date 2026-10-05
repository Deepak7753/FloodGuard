# FloodGuard 🌊

**AI/IoT-Based Early Warning System for Flood and Natural Disaster Management**

Live sensor monitoring with a rule-based alert engine, plus an XGBoost flood-severity predictor. Built with FastAPI, React and ESP32.

FloodGuard combines IoT sensing with machine learning. Its ML component estimates the probability of a **Severe Flood** from hydrometeorological, flood-event, catchment, climate and socio-economic features. The API then maps the model probability into application-defined **High / Moderate / Low** risk bands.

## Highlights

- **IoT layer** - sensor nodes (ESP32 firmware included) POST water level, rainfall, soil moisture and battery readings to the API
- **Rule-based early-warning engine** - water level vs. warning/danger levels, rate of rise (m/h) and rainfall intensity produce `NORMAL / WATCH / WARNING / DANGER`, with an alert log on every status change
- **Live Monitor dashboard** - station cards, 8-hour water-level chart with threshold lines, alert feed, auto-refresh, offline/low-battery detection
- **AI severity predictor** - XGBoost classifier that rates the severity of a flood event (INDOFLOODS data), with High / Moderate / Low bands
- **Hardware-free demo** - `iot_simulator.py` streams realistic scenarios (normal, slow rise, flash flood)
- FastAPI backend with Pydantic validation, API-key protected sensor writes, SQLite storage and OpenAPI docs
- React + Vite + Tailwind frontend, pytest test-suite

## Architecture

```text
 ESP32 node(s)  (ultrasonic level + rain gauge + battery)         iot_simulator.py
        │  POST /iot/readings  (X-API-Key)                              │
        └───────────────────────────┬───────────────────────────────────┘
                                    ▼
                         FastAPI  (main.py + iot.py)
        ┌───────────────────────────┼───────────────────────────────┐
        │ Rule engine + SQLite      │ /predict                      │
        │ rate of rise, thresholds, │ Pydantic → feature engineering │
        │ alerts, offline detection │ → encoder/imputer → XGBoost    │
        └───────────────────────────┴───────────────────────────────┘
                                    ▲ Axios (polls every 5 s)
                         React: Live Monitor | Severity Predictor
```

## How the two halves fit together

| | Live Monitor (IoT rules) | Severity Predictor (ML) |
|---|---|---|
| Question answered | "Is a river rising dangerously **right now**?" | "How **severe** is this flood event?" |
| Input | Live sensor readings | Recorded event, catchment and climate features |
| Method | Thresholds + rate of rise + rainfall | XGBoost on INDOFLOODS |
| Use for early warning | **Yes** | No - needs post-peak values such as peak flood level |

## Model framing

The bundled model is a **binary classifier** for `P(Severe Flood)`. The frontend/backend application converts that probability into risk bands using these thresholds:

- **High:** probability ≥ 0.65
- **Moderate:** 0.35–0.6499
- **Low:** probability < 0.35

These are application thresholds, not three classes directly predicted by XGBoost.

## Repository structure

```text
FloodGuard/
├── main.py                  # FastAPI app: /predict, /health, /schema
├── iot.py                   # IoT router: ingestion, SQLite, alert engine
├── iot_simulator.py         # Fake sensor network for demos
├── firmware/floodguard_node/floodguard_node.ino   # ESP32 sensor node
├── flood_xgboost_full.py    # Model training / evaluation
├── model_xgboost_full.pkl   # Bundled model
├── tests/test_api.py        # pytest suite (11 tests)
├── App.jsx                  # Shell: tabs + API health indicator
├── LiveMonitor.jsx          # IoT dashboard
├── Predictor.jsx            # Severity predictor form
├── api.js, main.jsx, index.html, index.css, vite.config.js
├── requirements.txt, requirements-dev.txt, package.json
├── dataset/, img/
└── .env.example
```

## Run locally

### 1. Backend

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start FastAPI:

```bash
uvicorn main:app --reload --port 8000
```

API documentation is available at `http://localhost:8000/docs`.

### 2. Frontend

In a second terminal:

```bash
npm install
npm run dev
```

Vite normally serves the frontend at `http://localhost:5173`.

For a different backend URL, create `.env` from `.env.example` and set:

```text
VITE_API_URL=http://localhost:8000
```

### 3. Stream demo sensor data

With the backend running, in a third terminal:

```bash
python iot_simulator.py
```

It backfills 8 hours of history (the Yamuna demo station ends in `DANGER`, Ganga in `WATCH`, the rest `NORMAL`) and then streams a live reading every 10 s. Open the **Live Monitor** tab.

### 4. Run the tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q tests
```

### 5. CORS

For local development the API allows `http://localhost:5173` by default. For deployment, set `CORS_ORIGINS` to a comma-separated list of trusted frontend origins.

Example:

```text
CORS_ORIGINS=https://your-frontend.example
```

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | API/model status |
| GET | `/health` | Health and model information |
| POST | `/predict` | Flood-risk prediction |
| GET | `/schema` | Allowed categorical values |
| POST | `/iot/readings` | Ingest a sensor reading (**needs `X-API-Key`**) |
| POST | `/iot/stations` | Register/update a station and its warning/danger levels (**needs `X-API-Key`**) |
| GET | `/iot/stations` | Stations with latest reading and live status |
| GET | `/iot/stations/{id}/history?hours=6` | Recent readings |
| GET | `/iot/alerts?limit=50` | Alert log (status changes), newest first |
| GET | `/docs` | Interactive Swagger/OpenAPI docs |

## IoT sensor nodes

Set the server key (`FLOODGUARD_API_KEY`) and send readings:

```bash
curl -X POST http://localhost:8000/iot/readings \
  -H "Content-Type: application/json" -H "X-API-Key: $FLOODGUARD_API_KEY" \
  -d '{"station_id":"YMN-01","water_level_m":204.2,"rain_mm_hr":12,"battery_pct":88}'
```

`firmware/floodguard_node/floodguard_node.ino` is a ready ESP32 sketch (JSN-SR04T ultrasonic sensor, tipping-bucket rain gauge, battery monitor). Fill in Wi-Fi, API URL, key, station ID and the surveyed sensor height before flashing.

**Alert rules** (constants at the top of `iot.py`, all tunable):

| Status | Triggered by (any) |
|---|---|
| WATCH | level within 0.5 m of warning level · rise ≥ 0.15 m/h · rain ≥ 25 mm/h |
| WARNING | level ≥ warning level · rise ≥ 0.30 m/h · rain ≥ 50 mm/h |
| DANGER | level ≥ danger level · above warning level **and** rising ≥ 0.30 m/h |
| OFFLINE | no reading for 15 min |

> The four demo stations ship with **placeholder** warning/danger levels. Replace them with the official levels from CWC / your state agency (`POST /iot/stations`) before using the system for anything real.

## Training

`flood_xgboost_full.py` contains the model-training and evaluation workflow. It expects the three INDOFLOODS CSV files inside `dataset/`.

The training workflow derives rainfall intensity, monsoon flag, rise rate and rainfall-per-day features, performs a stratified train/test split, fits categorical encoding and median imputation on the training data, evaluates the held-out test set, performs cross-validation, generates feature-importance/confusion-matrix plots, and saves the model bundle to `artifacts/model_xgboost_full.pkl`. Early stopping uses a validation slice carved from the training set, so the test set is never used for model selection. To serve a retrained model, set `FLOODGUARD_MODEL_PATH=artifacts/model_xgboost_full.pkl` and update `MODEL_META` in `main.py`.

**Dataset note:** the raw CSVs are not bundled in this repository. Verify the original dataset's license and redistribution terms before downloading, committing or redistributing them.

## Current bundled model

The API ships with `model_xgboost_full.pkl`, so the prediction demo can run without the training dataset. The backend source reports the bundled model as trained on 4,548 events from 155 gauge stations and reports a held-out ROC-AUC of 0.9732. Treat these as the metrics/metadata of the supplied artifact; retraining the model can produce different values.

## Known limitations (read before presenting)

- **The ML model is not a forecaster.** It uses values such as peak flood level and peak discharge, which are only known during/after an event. It rates severity; early warning in this project comes from the IoT rule engine.
- **Model sensitivity.** In testing, the model reacts strongly to peak flood level and catchment features; lowering rainfall at a fixed flood level can even raise the score. Treat it as an event-severity classifier, not a rainfall-driven predictor.
- **Rules are simple by design.** Thresholds are generic defaults, not calibrated per river. Real deployments need per-station calibration and validation against historical events.
- **Next steps for a stronger system:** a time-series forecaster (e.g. LSTM/gradient boosting on upstream gauge + rainfall forecast), SMS/WhatsApp/email alert delivery, MQTT/LoRaWAN transport for remote sites, authentication on the dashboard, and PostgreSQL for multi-user deployments.
- The bundled `.pkl` was serialised with an older XGBoost, so loading it prints a harmless warning. Retraining (or `model.save_model("model.json")`) removes it.

## Portfolio / interview talking points

Be prepared to explain:

- Why XGBoost was selected
- What the target variable represents
- How the 41 model features are constructed
- Why categorical values are encoded
- Why preprocessing must be fitted only on training data
- What ROC-AUC, precision, recall and F1 mean
- Why the model outputs a probability before risk-band thresholds are applied
- How React communicates with FastAPI using Axios
- Why Pydantic validation and CORS are used
- How the saved Joblib model bundle is loaded by the API
- How rate of rise is computed and why alerts fire only on status *changes* (no alert spam)
- Why the IoT rule engine, not the ML model, drives real-time warnings
- How an ESP32 converts ultrasonic distance into water level

## Important note

This project was developed with AI-assisted coding. Before presenting it in an interview, review the complete code yourself and make sure you can explain every major design choice, preprocessing step, API route and model decision.
