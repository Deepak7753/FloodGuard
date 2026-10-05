from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal, Optional
import joblib
import pandas as pd
from pathlib import Path
import time
import os
import logging

from iot import router as iot_router

log = logging.getLogger("floodguard")
STARTUP_TIME = time.time()
VERSION = "2.0.0"

# Application-defined risk bands applied to P(Severe Flood)
HIGH_THRESHOLD = 0.65
MODERATE_THRESHOLD = 0.35

# Metadata of the *bundled* artifact (update when you retrain)
MODEL_META = {
    "name": "XGBoost INDOFLOODS v1.0",
    "training_events": 4548,
    "gauge_stations": 155,
    "roc_auc": 0.9732,
    "cv_auc": "0.9682 ± 0.005",
    "source": "INDOFLOODS, IIT Delhi 2025 (Kuntla & Saharia, BAMS)",
}

MODEL_PATH = Path(os.getenv("FLOODGUARD_MODEL_PATH", Path(__file__).parent / "model_xgboost_full.pkl"))
bundle  = joblib.load(MODEL_PATH)
model   = bundle["model"]
imputer = bundle["imputer"]
encoder = bundle["encoder"]
FEATURES  = bundle["features"]
CAT_COLS  = bundle["cat_cols"]

app = FastAPI(
    title="FloodGuard API",
    description=(
        "AI/IoT early-warning backend. **/iot/** ingests live sensor readings and runs a "
        "rule-based alert engine; **/predict** runs an XGBoost classifier that rates the "
        "severity of a flood event (INDOFLOODS, IIT Delhi 2025)."
    ),
    version=VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)
app.include_router(iot_router)

class FloodInput(BaseModel):

    rainfall_1d:   float = Field(..., ge=0, description="Cumulative rainfall 1 day before peak (mm)")
    rainfall_3d:   float = Field(..., ge=0, description="Cumulative rainfall 3 days before peak (mm)")
    rainfall_5d:   float = Field(..., ge=0, description="Cumulative rainfall 5 days before peak (mm)")

    rainfall_7d:   Optional[float] = Field(None, ge=0, description="Cumulative rainfall 7 days before peak (mm). Optional — improves intensity features when provided.")
    rainfall_10d:  float = Field(..., ge=0, description="Cumulative rainfall 10 days before peak (mm)")

    peak_discharge:   Optional[float] = Field(None, ge=0,  description="Peak discharge (cumec). Optional.")
    flood_volume:     Optional[float] = Field(None, ge=0,  description="Flood volume (cumec). Optional.")
    event_duration:   int             = Field(..., ge=1,   description="Event duration (days)")
    time_to_peak:     int             = Field(..., ge=1,   description="Days from event start to peak")
    recession_time:   int             = Field(..., ge=1,   description="Days from peak to recession end")
    peak_flood_level: float           = Field(..., ge=0,   description="Peak flood water level (m)")
    num_peaks:        int             = Field(..., ge=1,   description="Number of peak flood levels")
    start_month:      int             = Field(..., ge=1, le=12, description="Month the flood started (1–12)")

    drainage_area:          float = Field(..., gt=0, description="Upstream catchment drainage area (km²)")
    catchment_relief:       float = Field(..., ge=0, description="Elevation difference in catchment (m)")
    drainage_density:       float = Field(..., ge=0, description="Total stream length / drainage area")
    ruggedness_number:      float = Field(..., ge=0, description="Catchment ruggedness index")
    stream_order:           int   = Field(..., ge=1, description="Strahler stream order")
    form_factor:            float = Field(..., ge=0, description="Catchment form factor")
    sinuosity_index:        float = Field(..., ge=1, description="Channel sinuosity")
    elongation_ratio:       float = Field(..., ge=0, description="Catchment elongation ratio")
    infiltration_number:    float = Field(..., ge=0, description="Catchment infiltration number")
    annual_mean_temp:       float = Field(...,       description="Annual mean temperature (°C)")
    annual_precipitation:   float = Field(..., ge=0, description="Mean annual precipitation (mm)")
    precip_wettest_month:   float = Field(..., ge=0, description="Precipitation of wettest month (mm)")
    precip_seasonality:     float = Field(..., ge=0, description="Precipitation seasonality (CV)")
    population_density:     float = Field(..., ge=0, description="Population per km²")
    urban_percentage:       float = Field(..., ge=0, le=100, description="% urban land cover in catchment")
    road_density:           float = Field(..., ge=0, description="Road density (km/km²)")
    hdi_2015:               float = Field(..., ge=0, le=1,   description="Human Development Index (2015)")
    night_light:            float = Field(..., ge=0, description="Night light intensity index")

    land_cover: Literal["Cropland", "Forest", "Mosaic vegetation", "No dominant class"] = Field(
        ..., description="Dominant land cover class in catchment"
    )
    soil_type: Literal[
        "Acrisols", "Cambisols", "Fluvisols", "Leptosols",
        "Lixisols", "Luvisols", "No dominant class", "Vertisols"
    ] = Field(..., description="Dominant soil type")
    koppen_climate: Literal["Arid", "No dominant class", "Temperate", "Tropical"] = Field(
        ..., description="Köppen-Geiger climate classification"
    )
    lithology: Literal[
        "Acid plutonic rocks", "Basic volcanic rocks", "Metamorphics",
        "No dominant class", "Siliciclastic sedimentary rocks", "Unconsolidated sediments"
    ] = Field(..., description="Dominant lithology type")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary": "High Risk — Tropical monsoon, large catchment",
                    "description": "August monsoon event, Tropical/Vertisols, 420mm over 10 days. Expect ~96% severe flood.",
                    "value": {
                        "rainfall_1d": 95.0, "rainfall_3d": 210.0, "rainfall_5d": 310.0,
                        "rainfall_7d": 370.0, "rainfall_10d": 420.0,
                        "peak_discharge": 12000.0, "flood_volume": None,
                        "event_duration": 4, "time_to_peak": 1, "recession_time": 3,
                        "peak_flood_level": 28.5, "num_peaks": 2, "start_month": 8,
                        "drainage_area": 18000.0, "catchment_relief": 1800, "drainage_density": 0.00018,
                        "ruggedness_number": 0.32, "stream_order": 6, "form_factor": 0.29,
                        "sinuosity_index": 1.55, "elongation_ratio": 1.8e-10, "infiltration_number": 2.5e-12,
                        "annual_mean_temp": 26.0, "annual_precipitation": 2100.0,
                        "precip_wettest_month": 620.0, "precip_seasonality": 135.0,
                        "population_density": 850.0, "urban_percentage": 28.0,
                        "road_density": 420.0, "hdi_2015": 0.58, "night_light": 4.2,
                        "land_cover": "Cropland", "soil_type": "Vertisols",
                        "koppen_climate": "Tropical", "lithology": "Unconsolidated sediments",
                    }
                },
                {
                    "summary": "Moderate Risk — Tropical Cropland, August, mixed signals",
                    "description": "August monsoon event, Tropical/Luvisols, 329mm over 10 days but only a 9 m peak level. Expect ~50% severe flood.",
                    "value": {
                        "rainfall_1d": 30.0, "rainfall_3d": 110.0, "rainfall_5d": 200.0,
                        "rainfall_7d": 270.0, "rainfall_10d": 329.0,
                        "peak_discharge": None, "flood_volume": None,
                        "event_duration": 3, "time_to_peak": 2, "recession_time": 2,
                        "peak_flood_level": 9.0, "num_peaks": 1, "start_month": 8,
                        "drainage_area": 21904.0, "catchment_relief": 1204, "drainage_density": 0.000162,
                        "ruggedness_number": 0.195, "stream_order": 5, "form_factor": 0.188,
                        "sinuosity_index": 1.404, "elongation_ratio": 7.02e-11, "infiltration_number": 2.95e-12,
                        "annual_mean_temp": 25.3, "annual_precipitation": 1214.0,
                        "precip_wettest_month": 306.0, "precip_seasonality": 116.0,
                        "population_density": 723.0, "urban_percentage": 42.3,
                        "road_density": 433.0, "hdi_2015": 0.547, "night_light": 7.76,
                        "land_cover": "Cropland", "soil_type": "Luvisols",
                        "koppen_climate": "Tropical", "lithology": "Metamorphics",
                    }
                },
                {
                    "summary": "Low Risk — Arid zone, small catchment, March",
                    "description": "Non-monsoon Arid/Leptosols event, 25mm over 10 days. Expect ~1% severe flood.",
                    "value": {
                        "rainfall_1d": 5.0, "rainfall_3d": 12.0, "rainfall_5d": 18.0,
                        "rainfall_7d": 22.0, "rainfall_10d": 25.0,
                        "peak_discharge": 180.0, "flood_volume": None,
                        "event_duration": 2, "time_to_peak": 1, "recession_time": 1,
                        "peak_flood_level": 4.2, "num_peaks": 1, "start_month": 3,
                        "drainage_area": 320.0, "catchment_relief": 280, "drainage_density": 0.00012,
                        "ruggedness_number": 0.04, "stream_order": 2, "form_factor": 0.55,
                        "sinuosity_index": 1.12, "elongation_ratio": 6.0e-11, "infiltration_number": 2.2e-12,
                        "annual_mean_temp": 29.0, "annual_precipitation": 620.0,
                        "precip_wettest_month": 95.0, "precip_seasonality": 88.0,
                        "population_density": 45.0, "urban_percentage": 2.0,
                        "road_density": 80.0, "hdi_2015": 0.51, "night_light": 0.3,
                        "land_cover": "No dominant class", "soil_type": "Leptosols",
                        "koppen_climate": "Arid", "lithology": "Metamorphics",
                    }
                },
            ]
        }
    }

class PredictionResponse(BaseModel):
    risk_score:  float
    risk_label:  Literal["High", "Moderate", "Low"]
    confidence:  str
    model_notes: str

def build_feature_df(inp: FloodInput) -> pd.DataFrame:
    is_monsoon = 1 if 6 <= inp.start_month <= 9 else 0

    r7 = inp.rainfall_7d if inp.rainfall_7d is not None else (
        inp.rainfall_5d + (inp.rainfall_10d - inp.rainfall_5d) * (2 / 5)
    )

    intensity_d2_3  = inp.rainfall_3d - inp.rainfall_1d
    intensity_d4_7  = r7              - inp.rainfall_3d
    intensity_d8_10 = inp.rainfall_10d - r7

    rise_rate    = inp.peak_flood_level / max(inp.time_to_peak, 1)
    rain_per_day = inp.rainfall_10d     / max(inp.event_duration, 1)

    row = {
        "rainfall_1d":               inp.rainfall_1d,
        "rainfall_3d":               inp.rainfall_3d,
        "rainfall_5d":               inp.rainfall_5d,
        "rainfall_10d":              inp.rainfall_10d,
        "intensity_d1":              inp.rainfall_1d,
        "intensity_d2_3":            intensity_d2_3,
        "intensity_d4_7":            intensity_d4_7,
        "intensity_d8_10":           intensity_d8_10,
        "Peak Discharge Q (cumec)":  inp.peak_discharge,
        "Flood Volume (cumec)":      inp.flood_volume,
        "Event Duration (days)":     inp.event_duration,
        "Time to Peak (days)":       inp.time_to_peak,
        "Recession Time (day)":      inp.recession_time,
        "Peak Flood Level (m)":      inp.peak_flood_level,
        "Num Peak FL":               inp.num_peaks,
        "rise_rate":                 rise_rate,
        "rain_per_day":              rain_per_day,
        "start_month":               inp.start_month,
        "is_monsoon":                is_monsoon,
        "Drainage Area":             inp.drainage_area,
        "Catchment Relief":          inp.catchment_relief,
        "Drainage Density":          inp.drainage_density,
        "Ruggedness Number":         inp.ruggedness_number,
        "Stream Order":              inp.stream_order,
        "Form Factor":               inp.form_factor,
        "Sinuosity Index":           inp.sinuosity_index,
        "Elongation Ratio":          inp.elongation_ratio,
        "Infiltration Number":       inp.infiltration_number,
        "Annual Mean Temperature":   inp.annual_mean_temp,
        "Annual Precipitation":      inp.annual_precipitation,
        "Precipitation of Wettest Month": inp.precip_wettest_month,
        "Precipitation Seasonality": inp.precip_seasonality,
        "Population Density":        inp.population_density,
        "Urban percentage":          inp.urban_percentage,
        "Road Density":              inp.road_density,
        "2015_HDI":                  inp.hdi_2015,
        "Night Light":               inp.night_light,
        "Land cover":                inp.land_cover,
        "Soil type":                 inp.soil_type,
        "KoppenGeiger Climate Type": inp.koppen_climate,
        "lithology type":            inp.lithology,
    }
    return pd.DataFrame([row], columns=FEATURES)

@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "model": MODEL_META["name"], "features": len(FEATURES)}

@app.get("/health", tags=["Health"], summary="Health check with model status and uptime")
def health():
    uptime_seconds = int(time.time() - STARTUP_TIME)
    hours, rem = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return {
        "status": "healthy",
        "version": VERSION,
        "uptime": f"{hours:02d}:{minutes:02d}:{seconds:02d}",
        "uptime_seconds": uptime_seconds,
        "model": {
            **MODEL_META,
            "algorithm": "XGBoost (gradient boosted trees)",
            "features": len(FEATURES),
            "numeric_features": len(bundle["num_cols"]),
            "categorical_features": len(CAT_COLS),
            "loaded": True,
        },
        "risk_thresholds": {"high": HIGH_THRESHOLD, "moderate": MODERATE_THRESHOLD},
        "endpoints": ["/", "/health", "/predict", "/schema", "/iot/stations", "/iot/alerts", "/docs"],
    }

@app.post("/predict", response_model=PredictionResponse, tags=["Prediction"],
          summary="Predict flood severity from hydrometeorological and catchment features")
def predict(inp: FloodInput):
    try:
        df = build_feature_df(inp)
        df[CAT_COLS] = encoder.transform(df[CAT_COLS])
        df_imp = pd.DataFrame(imputer.transform(df), columns=FEATURES)
        proba = float(model.predict_proba(df_imp)[0][1])

        if proba >= HIGH_THRESHOLD:
            label, confidence = "High", f"{proba:.1%} probability of severe flood — immediate monitoring advised"
        elif proba >= MODERATE_THRESHOLD:
            label, confidence = "Moderate", f"{proba:.1%} — borderline severity, monitor closely"
        else:
            label, confidence = "Low", f"{proba:.1%} probability of severe flood — standard monitoring"

        return PredictionResponse(
            risk_score=round(proba, 4),
            risk_label=label,
            confidence=confidence,
            model_notes=(
                f"XGBoost trained on {MODEL_META['training_events']:,} real flood events from "
                f"{MODEL_META['gauge_stations']} CWC gauge stations ({MODEL_META['source']}). "
                f"ROC-AUC: {MODEL_META['roc_auc']:.3f} on held-out test set. "
                "Rates the severity of an observed flood event; it is not a forecast."
            ),
        )
    except Exception:
        log.exception("Prediction failed")
        raise HTTPException(status_code=500, detail="Internal prediction error. See server logs.")

@app.get("/schema", tags=["Info"])
def schema():
    """Returns allowed values for all categorical fields."""
    return {
        "land_cover":    ["Cropland", "Forest", "Mosaic vegetation", "No dominant class"],
        "soil_type":     ["Acrisols", "Cambisols", "Fluvisols", "Leptosols",
                          "Lixisols", "Luvisols", "No dominant class", "Vertisols"],
        "koppen_climate":["Arid", "No dominant class", "Temperate", "Tropical"],
        "lithology":     ["Acid plutonic rocks", "Basic volcanic rocks", "Metamorphics",
                          "No dominant class", "Siliciclastic sedimentary rocks",
                          "Unconsolidated sediments"],
    }
