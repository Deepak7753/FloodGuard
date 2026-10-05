"""FloodGuard IoT layer: sensor ingestion, SQLite storage and a rule-based
early-warning engine.

Sensor nodes (ESP32 etc.) POST readings to /iot/readings. For every reading the
engine computes the rate of rise of the water level and evaluates it, together
with rainfall intensity, against per-station warning/danger levels.

All thresholds below are TUNABLE DEFAULTS, not official values. Replace the
demo station levels with the official CWC/state-agency levels for real use.
"""
import hmac
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

log = logging.getLogger("floodguard.iot")
router = APIRouter(prefix="/iot", tags=["IoT"])

STATUS_ORDER = ["NORMAL", "WATCH", "WARNING", "DANGER"]

# Engine thresholds (tunable)
LEVEL_WATCH_MARGIN_M = 0.5   # WATCH when within this distance below the warning level
RATE_WATCH_M_HR = 0.15       # rate of rise (m/hour)
RATE_WARNING_M_HR = 0.30
RAIN_WATCH_MM_HR = 25.0      # rainfall intensity (mm/hour)
RAIN_WARNING_MM_HR = 50.0
RATE_WINDOW_S = 3600         # look-back window for rate of rise
RATE_MIN_SPAN_S = 600        # need at least 10 min of data for a rate
OFFLINE_AFTER_S = 15 * 60    # no data for this long => station OFFLINE
LOW_BATTERY_PCT = 20

# Illustrative demo stations. Warning/danger levels are placeholders.
DEMO_STATIONS = [
    ("YMN-01", "Yamuna - Delhi (demo)", "Yamuna", 28.66, 77.25, 204.50, 205.33),
    ("GNG-01", "Ganga - Patna (demo)", "Ganga", 25.62, 85.14, 48.00, 48.60),
    ("BRM-01", "Brahmaputra - Guwahati (demo)", "Brahmaputra", 26.18, 91.74, 49.00, 49.68),
    ("MHN-01", "Mahanadi - Cuttack (demo)", "Mahanadi", 20.46, 85.88, 25.00, 26.00),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS stations (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, river TEXT, lat REAL, lon REAL,
    warning_level_m REAL NOT NULL, danger_level_m REAL NOT NULL);
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, station_id TEXT NOT NULL, ts REAL NOT NULL,
    water_level_m REAL NOT NULL, rain_mm_hr REAL, soil_moisture_pct REAL, battery_pct REAL,
    rate_m_hr REAL, status TEXT NOT NULL, reasons TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS idx_readings_station_ts ON readings(station_id, ts);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, station_id TEXT NOT NULL, ts REAL NOT NULL,
    status TEXT NOT NULL, previous_status TEXT NOT NULL, message TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts);
"""

_initialized: set = set()


def _db_path() -> str:
    return os.getenv("FLOODGUARD_DB", str(Path(__file__).parent / "floodguard.db"))


@contextmanager
def connect():
    path = _db_path()
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        if path not in _initialized:
            conn.executescript(SCHEMA)
            if os.getenv("FLOODGUARD_SEED_DEMO", "1") == "1":
                conn.executemany("INSERT OR IGNORE INTO stations VALUES (?,?,?,?,?,?,?)", DEMO_STATIONS)
            conn.commit()
            _initialized.add(path)
        yield conn
        conn.commit()
    finally:
        conn.close()


def require_api_key(x_api_key: Optional[str] = Header(None)):
    expected = os.getenv("FLOODGUARD_API_KEY", "dev-key-change-me")
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


# ---------------------------------------------------------------- engine

def evaluate(level: float, warn: float, danger: float,
             rate: Optional[float], rain: Optional[float]):
    """Return (status, reasons) for one reading."""
    score = 0
    reasons = []

    def bump(s: int, why: str):
        nonlocal score
        score = max(score, s)
        reasons.append(why)

    if level >= danger:
        bump(3, f"Water level {level:.2f} m is above the danger level ({danger:.2f} m)")
    elif level >= warn:
        bump(2, f"Water level {level:.2f} m is above the warning level ({warn:.2f} m)")
    elif level >= warn - LEVEL_WATCH_MARGIN_M:
        bump(1, f"Water level {level:.2f} m is within {LEVEL_WATCH_MARGIN_M} m of the warning level")

    if rate is not None:
        if rate >= RATE_WARNING_M_HR:
            bump(2, f"Water rising fast: {rate:.2f} m/h")
        elif rate >= RATE_WATCH_M_HR:
            bump(1, f"Water rising: {rate:.2f} m/h")
        if level >= warn and rate >= RATE_WARNING_M_HR:
            bump(3, "Above warning level AND rising fast")

    if rain is not None:
        if rain >= RAIN_WARNING_MM_HR:
            bump(2, f"Extreme rainfall intensity: {rain:.0f} mm/h")
        elif rain >= RAIN_WATCH_MM_HR:
            bump(1, f"Heavy rainfall intensity: {rain:.0f} mm/h")

    return STATUS_ORDER[score], reasons


def rate_of_rise(conn, station_id: str, ts: float, level: float) -> Optional[float]:
    """Rise (m/hour) between the oldest reading in the look-back window and this one."""
    row = conn.execute(
        "SELECT ts, water_level_m FROM readings WHERE station_id=? AND ts>=? AND ts<? "
        "ORDER BY ts ASC LIMIT 1",
        (station_id, ts - RATE_WINDOW_S, ts),
    ).fetchone()
    if row is None or ts - row["ts"] < RATE_MIN_SPAN_S:
        return None
    return (level - row["water_level_m"]) / ((ts - row["ts"]) / 3600.0)


# ---------------------------------------------------------------- models

class Reading(BaseModel):
    station_id: str = Field(..., min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    water_level_m: float = Field(..., ge=-100, le=9000, description="Water level (m): gauge datum or reduced level above MSL")
    rain_mm_hr: Optional[float] = Field(None, ge=0, le=500, description="Rainfall intensity (mm/h)")
    soil_moisture_pct: Optional[float] = Field(None, ge=0, le=100)
    battery_pct: Optional[float] = Field(None, ge=0, le=100)
    ts: Optional[float] = Field(None, description="Unix epoch seconds; defaults to server time")


class StationIn(BaseModel):
    id: str = Field(..., min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(..., min_length=1, max_length=120)
    river: Optional[str] = None
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lon: Optional[float] = Field(None, ge=-180, le=180)
    warning_level_m: float
    danger_level_m: float


# ---------------------------------------------------------------- endpoints

@router.post("/readings", summary="Ingest one sensor reading (requires X-API-Key)")
def ingest(r: Reading, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    now = time.time()
    ts = r.ts if r.ts is not None else now
    if ts > now + 60 or ts < now - 7 * 86400:
        raise HTTPException(422, "ts must be within the last 7 days and not in the future")

    with connect() as conn:
        st = conn.execute("SELECT * FROM stations WHERE id=?", (r.station_id,)).fetchone()
        if st is None:
            raise HTTPException(404, f"Unknown station '{r.station_id}'. Register it first.")

        rate = rate_of_rise(conn, r.station_id, ts, r.water_level_m)
        status, reasons = evaluate(r.water_level_m, st["warning_level_m"],
                                   st["danger_level_m"], rate, r.rain_mm_hr)
        if r.battery_pct is not None and r.battery_pct < LOW_BATTERY_PCT:
            reasons.append(f"Low battery: {r.battery_pct:.0f}%")

        prev = conn.execute(
            "SELECT status FROM readings WHERE station_id=? AND ts<? ORDER BY ts DESC LIMIT 1",
            (r.station_id, ts),
        ).fetchone()
        prev_status = prev["status"] if prev else "NORMAL"

        conn.execute(
            "INSERT INTO readings (station_id, ts, water_level_m, rain_mm_hr, soil_moisture_pct, "
            "battery_pct, rate_m_hr, status, reasons) VALUES (?,?,?,?,?,?,?,?,?)",
            (r.station_id, ts, r.water_level_m, r.rain_mm_hr, r.soil_moisture_pct,
             r.battery_pct, rate, status, " | ".join(reasons)),
        )
        alert_raised = False
        if status != prev_status:
            direction = "escalated" if STATUS_ORDER.index(status) > STATUS_ORDER.index(prev_status) else "eased"
            msg = f"{st['name']}: {direction} {prev_status} -> {status}. " + "; ".join(reasons)
            conn.execute(
                "INSERT INTO alerts (station_id, ts, status, previous_status, message) VALUES (?,?,?,?,?)",
                (r.station_id, ts, status, prev_status, msg.strip()),
            )
            alert_raised = True
            log.warning("ALERT %s", msg)

    return {"station_id": r.station_id, "status": status, "rate_m_hr": rate,
            "reasons": reasons, "alert_raised": alert_raised}


@router.post("/stations", summary="Register or update a station (requires X-API-Key)")
def upsert_station(s: StationIn, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    if s.danger_level_m <= s.warning_level_m:
        raise HTTPException(422, "danger_level_m must be greater than warning_level_m")
    with connect() as conn:
        conn.execute(
            "INSERT INTO stations VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "name=excluded.name, river=excluded.river, lat=excluded.lat, lon=excluded.lon, "
            "warning_level_m=excluded.warning_level_m, danger_level_m=excluded.danger_level_m",
            (s.id, s.name, s.river, s.lat, s.lon, s.warning_level_m, s.danger_level_m),
        )
    return {"ok": True, "id": s.id}


@router.get("/stations", summary="All stations with their latest reading and live status")
def list_stations():
    now = time.time()
    out = []
    with connect() as conn:
        for st in conn.execute("SELECT * FROM stations ORDER BY id").fetchall():
            last = conn.execute(
                "SELECT * FROM readings WHERE station_id=? ORDER BY ts DESC LIMIT 1", (st["id"],)
            ).fetchone()
            item = dict(st)
            if last is None:
                item.update(status="NO_DATA", last_status=None, latest=None, age_s=None, reasons=[])
            else:
                age = now - last["ts"]
                item.update(
                    status="OFFLINE" if age > OFFLINE_AFTER_S else last["status"],
                    last_status=last["status"],
                    age_s=int(age),
                    reasons=[x for x in last["reasons"].split(" | ") if x],
                    latest={k: last[k] for k in ("ts", "water_level_m", "rain_mm_hr",
                                                 "soil_moisture_pct", "battery_pct", "rate_m_hr")},
                )
            out.append(item)
    return {"stations": out, "server_time": now}


@router.get("/stations/{station_id}/history", summary="Recent readings for one station")
def history(station_id: str, hours: float = Query(6, gt=0, le=168)):
    with connect() as conn:
        if conn.execute("SELECT 1 FROM stations WHERE id=?", (station_id,)).fetchone() is None:
            raise HTTPException(404, f"Unknown station '{station_id}'")
        rows = conn.execute(
            "SELECT ts, water_level_m, rain_mm_hr, rate_m_hr, status FROM readings "
            "WHERE station_id=? AND ts>=? ORDER BY ts ASC",
            (station_id, time.time() - hours * 3600),
        ).fetchall()
    return {"station_id": station_id, "readings": [dict(r) for r in rows]}


@router.get("/alerts", summary="Most recent alerts (status changes), newest first")
def alerts(limit: int = Query(50, ge=1, le=500)):
    with connect() as conn:
        rows = conn.execute("SELECT * FROM alerts ORDER BY ts DESC, id DESC LIMIT ?", (limit,)).fetchall()
    return {"alerts": [dict(r) for r in rows]}
