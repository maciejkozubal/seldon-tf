"""Data scientist side. Plain XGBoost — no TrueFoundry import anywhere.

Same handoff shape as train_sklearn.py, so the MLOps engineer runs the identical
deploy command against either folder.

    python scripts/train_xgboost.py
"""

import argparse
import json
from pathlib import Path

import joblib
from sklearn.datasets import load_iris
from xgboost import XGBClassifier


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="artifacts/iris-xgb", type=Path)
    args = ap.parse_args()

    X, y = load_iris(return_X_y=True)
    model = XGBClassifier(n_estimators=10).fit(X, y)

    # Named after the case, not a generic model.joblib — readable in the registry
    # and in the generated server.py. The deploy side reads it back off meta.json.
    model_file = f"{args.out.name}.joblib"

    args.out.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, args.out / model_file)
    (args.out / "sample_input.json").write_text(json.dumps(X[:5].tolist(), indent=2))
    (args.out / "meta.json").write_text(json.dumps(
        {"framework": "xgboost", "model_file": model_file}, indent=2))

    print(f"handoff ready: {args.out}")
    print(f"  next: python scripts/deploy_and_test.py --artifact {args.out} --server fastapi")


if __name__ == "__main__":
    main()
