"""Trains a model on made-up normal measures, then checks the /predict route.

From ml_api/:  python -m tests.test_predict   (or pytest)
Needs httpx for FastAPI's TestClient. The model goes to a temporary file: models/ is untouched.
"""

import os
import tempfile
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from app.features import FEATURES
from train import load_training_rows, train

TOKEN = "test-token"


def make_client():
    """Normal behaviour: heatsink 18-24 °C, cellar 14.5-16 °C, fan 1500-2100 rpm."""
    random = np.random.default_rng(0)
    rows = pd.DataFrame({
        "peltier_temp": random.uniform(18, 24, 2000),
        "ambient_temp": random.uniform(14.5, 16, 2000),
        "fan_rpm": random.integers(1500, 2100, 2000),
    })
    model_file = Path(tempfile.mkdtemp()) / "model.joblib"
    joblib.dump(train(rows), model_file)

    # Read when app.main is imported, so set before the import
    os.environ["API_TOKEN"] = TOKEN
    os.environ["ML_MODEL_PATH"] = str(model_file)
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def post(client, token=TOKEN, **fields):
    body = {"peltier_id": "peltier_1", "is_on": True, "peltier_temp": 21, "ambient_temp": 15.2, "fan_rpm": 1800}
    body.update(fields)
    return client.post("/predict", json=body, headers={"Authorization": f"Bearer {token}"})


def test_predict():
    client = make_client()

    assert post(client).json()["is_anomaly"] is False
    # Fan stopped while the heatsink overheats
    assert post(client, peltier_temp=45, fan_rpm=0).json()["is_anomaly"] is True
    # Missing measure or stopped Peltier: no opinion
    assert post(client, fan_rpm=None).json()["is_anomaly"] is None
    assert post(client, is_on=False).json()["is_anomaly"] is None
    # Wrong token, absurd value
    assert post(client, token="wrong").status_code == 401
    assert post(client, fan_rpm=-5).status_code == 422


def test_training_rows_skip_old_stopped_and_incomplete_rows():
    csv_file = Path(tempfile.mkdtemp()) / "peltier.csv"
    csv_file.write_text(
        "peltier_id,peltier_temp,ambient_temp,fan_rpm,is_on,created_at\n"
        "peltier_1,20,15,1800,t,2026-11-04 13:00:00+00\n"   # before the repair
        "peltier_1,20,15,1800,t,2026-11-06 13:00:00+00\n"   # kept
        "peltier_1,20,15,,t,2026-11-06 13:01:00+00\n"       # rpm missing
        "peltier_1,20,15,0,f,2026-11-06 13:02:00+00\n",     # stopped
        encoding="utf-8",
    )
    rows = load_training_rows(csv_file, "2026-11-05 10:00+01:00")
    assert len(rows) == 1
    assert list(rows[FEATURES].iloc[0]) == [20, 15, 1800]


if __name__ == "__main__":
    test_predict()
    test_training_rows_skip_old_stopped_and_incomplete_rows()
    print("OK")
