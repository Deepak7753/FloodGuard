"""Simulate FloodGuard sensor nodes so the dashboard can be demoed without hardware.

    python iot_simulator.py                  # backfill 8h of history, then stream live
    python iot_simulator.py --no-backfill    # live stream only
    python iot_simulator.py --once           # backfill and exit

Uses only the standard library. Station thresholds are read from the API, and
each demo station follows a scenario: normal / rising / flash.
"""
import argparse
import json
import math
import os
import random
import time
import urllib.error
import urllib.request

SCENARIOS = {"YMN-01": "flash", "GNG-01": "rising", "BRM-01": "normal", "MHN-01": "normal"}
STEP_MIN = 5
BACKFILL_HOURS = 8.0


def level_at(scenario: str, warn: float, danger: float, t_h: float) -> tuple[float, float]:
    """Return (water_level_m, rain_mm_hr) at simulated hour t_h."""
    noise = random.gauss(0, 0.01)
    if scenario == "flash":              # flat for 5 h, then ~1.1 m/h surge
        base, ramp = warn - 2.0, max(0.0, t_h - 5.0)
        return base + 1.1 * ramp + noise, min(70.0, 4 + 22 * ramp) + random.random()
    if scenario == "rising":             # slow, steady rise
        return warn - 1.6 + 0.2 * t_h + noise, 6 + 1.5 * t_h + random.random() * 3
    return warn - 2.5 + 0.05 * math.sin(t_h) + noise, random.random() * 2


def call(url: str, key: str, payload: dict | None = None):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json", "X-API-Key": key},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=os.getenv("FLOODGUARD_API", "http://localhost:8000"))
    ap.add_argument("--key", default=os.getenv("FLOODGUARD_API_KEY", "dev-key-change-me"))
    ap.add_argument("--interval", type=float, default=10, help="seconds between live readings")
    ap.add_argument("--no-backfill", action="store_true")
    ap.add_argument("--once", action="store_true", help="backfill only, then exit")
    a = ap.parse_args()

    try:
        stations = call(f"{a.api}/iot/stations", a.key)["stations"]
    except (urllib.error.URLError, OSError) as e:
        raise SystemExit(f"Cannot reach API at {a.api}: {e}\nStart it with: uvicorn main:app --port 8000")
    stations = [s for s in stations if s["id"] in SCENARIOS] or stations
    battery = {s["id"]: random.uniform(70, 100) for s in stations}

    def post(s, ts, t_h):
        lvl, rain = level_at(SCENARIOS.get(s["id"], "normal"), s["warning_level_m"], s["danger_level_m"], t_h)
        battery[s["id"]] = max(5.0, battery[s["id"]] - 0.002)
        return call(f"{a.api}/iot/readings", a.key, {
            "station_id": s["id"], "ts": ts, "water_level_m": round(lvl, 3),
            "rain_mm_hr": round(rain, 1), "soil_moisture_pct": round(random.uniform(40, 90), 1),
            "battery_pct": round(battery[s["id"]], 1),
        })

    now = time.time()
    steps = int(BACKFILL_HOURS * 60 / STEP_MIN)
    if not a.no_backfill:
        print(f"Backfilling {BACKFILL_HOURS:.0f} h for {len(stations)} stations ...")
        for i in range(steps):
            for s in stations:
                post(s, now - (steps - 1 - i) * STEP_MIN * 60, i * STEP_MIN / 60)
    if a.once:
        return

    print(f"Streaming live readings every {a.interval:.0f}s (Ctrl+C to stop)")
    t0 = time.time()
    offset = 0.0 if a.no_backfill else BACKFILL_HOURS
    while True:
        time.sleep(a.interval)
        t_h = offset + (time.time() - t0) / 3600
        line = []
        for s in stations:
            res = post(s, time.time(), t_h)
            line.append(f"{s['id']}={res['status']}")
        print(time.strftime("%H:%M:%S"), "  ".join(line))


if __name__ == "__main__":
    main()
