from pathlib import Path

import os

import joblib
import pandas as pd
from fastapi import Depends, FastAPI

from app.features import FEATURES
from app.schemas import PeltierMeasurement
from app.security import verify_token

# Default built from this file's location: works whatever folder the server is started from.
# ML_MODEL_PATH lets the tests use another file.
DEFAULT_MODEL = Path(__file__).resolve().parent.parent / "models" / "isolation_forest.joblib"
model = joblib.load(os.getenv("ML_MODEL_PATH", DEFAULT_MODEL))

# Public server: the route list is not published
app = FastAPI(title="Winnery ML API", docs_url=None, redoc_url=None, openapi_url=None)


@app.post("/predict", dependencies=[Depends(verify_token)])
def predict(measurement: PeltierMeasurement):
    values = measurement.model_dump()
    if not measurement.is_on or any(values[name] is None for name in FEATURES):
        # The model only learned running Peltiers with complete measures: no opinion otherwise
        return {"peltier_id": measurement.peltier_id, "is_anomaly": None, "anomaly_score": None}

    features = pd.DataFrame([{name: values[name] for name in FEATURES}])
    return {
        "peltier_id": measurement.peltier_id,
        "is_anomaly": bool(model.predict(features)[0] == -1),
        "anomaly_score": float(model.decision_function(features)[0]),  # below 0: unusual
    }
