"""Trains the anomaly model from a CSV export of the peltier table.

From ml_api/:  python train.py data/peltier.csv "2026-11-05 10:00+01:00"

The date is required: rows before it are ignored. Use the moment the wiring was
last repaired, so the model never learns hardware faults as "normal".
"""

import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest

from app.features import FEATURES

MODEL_PATH = Path(__file__).resolve().parent / "models" / "isolation_forest.joblib"


def load_training_rows(csv_path, clean_since):
    """Running Peltiers only, after clean_since, with every feature known."""
    data = pd.read_csv(csv_path)
    data["created_at"] = pd.to_datetime(data["created_at"], utc=True)
    # psql writes booleans as t/f
    data["is_on"] = data["is_on"].astype(str).str.lower().isin(["t", "true", "1"])
    data = data[(data["created_at"] >= pd.Timestamp(clean_since)) & data["is_on"]]
    return data.dropna(subset=FEATURES)


def train(data):
    # contamination="auto": no guess about the share of anomalies in the data
    # random_state=0: the same CSV always gives the same model
    model = IsolationForest(contamination="auto", random_state=0)
    model.fit(data[FEATURES])
    return model


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    rows = load_training_rows(sys.argv[1], sys.argv[2])
    if len(rows) < 100:
        sys.exit(f"Only {len(rows)} usable rows: too few to learn anything")
    if len(rows) < 1000:
        print(f"Warning: only {len(rows)} usable rows, retrain when more measures are collected")
    model = train(rows)
    MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    share = (model.predict(rows[FEATURES]) == -1).mean()
    print(f"{len(rows)} rows used, model saved to {MODEL_PATH}")
    print(f"{share:.1%} of training rows flagged (above 5-10%: the data is probably not clean)")
