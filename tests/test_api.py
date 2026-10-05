import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import main  # noqa: E402

KEY = {"X-API-Key": "test-key"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOODGUARD_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("FLOODGUARD_API_KEY", "test-key")
    return TestClient(main.app)


def example(i):
    return main.FloodInput.model_config["json_schema_extra"]["examples"][i]["value"]


# ---------------------------------------------------------------- ML API
def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "healthy" and body["model"]["features"] == 41


@pytest.mark.parametrize("i,label", [(0, "High"), (1, "Moderate"), (2, "Low")])
def test_predict_examples(client, i, label):
    r = client.post("/predict", json=example(i))
    assert r.status_code == 200
    assert r.json()["risk_label"] == label


def test_predict_validation(client):
    bad = {**example(0), "start_month": 13}
    assert client.post("/predict", json=bad).status_code == 422


# ---------------------------------------------------------------- IoT
def post(client, **kw):
    payload = {"station_id": "GNG-01", "water_level_m": 45.0, **kw}
    return client.post("/iot/readings", json=payload, headers=KEY)


def test_requires_api_key(client):
    r = client.post("/iot/readings", json={"station_id": "GNG-01", "water_level_m": 45})
    assert r.status_code == 401


def test_unknown_station_and_bad_value(client):
    assert post(client, station_id="NOPE").status_code == 404
    assert post(client, water_level_m=99999).status_code == 422


def test_normal_then_danger_creates_alert(client):
    assert post(client).json()["status"] == "NORMAL"          # GNG-01 warn 48.0 / danger 48.6
    res = post(client, water_level_m=48.9).json()
    assert res["status"] == "DANGER" and res["alert_raised"]
    alerts = client.get("/iot/alerts").json()["alerts"]
    assert alerts[0]["status"] == "DANGER" and alerts[0]["previous_status"] == "NORMAL"
    assert post(client, water_level_m=48.9).json()["alert_raised"] is False   # no spam


def test_rate_of_rise_triggers_warning(client):
    now = time.time()
    post(client, water_level_m=44.0, ts=now - 1800)
    res = post(client, water_level_m=44.4, ts=now).json()      # +0.4 m in 30 min = 0.8 m/h
    assert res["status"] == "WARNING"
    assert res["rate_m_hr"] == pytest.approx(0.8, rel=0.01)


def test_heavy_rain_triggers_watch(client):
    assert post(client, rain_mm_hr=30).json()["status"] == "WATCH"


def test_stations_history_and_offline(client):
    post(client, water_level_m=44.0, ts=time.time() - 3600)    # stale reading
    gng = {s["id"]: s for s in client.get("/iot/stations").json()["stations"]}
    assert gng["GNG-01"]["status"] == "OFFLINE"
    assert gng["BRM-01"]["status"] == "NO_DATA"
    post(client)                                               # fresh reading
    gng = {s["id"]: s for s in client.get("/iot/stations").json()["stations"]}
    assert gng["GNG-01"]["status"] == "NORMAL"
    hist = client.get("/iot/stations/GNG-01/history?hours=2").json()["readings"]
    assert len(hist) == 2
