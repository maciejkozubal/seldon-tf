"""Data scientist side. Plain scikit-learn — no TrueFoundry import anywhere.

Produces the handoff folder an MLOps engineer receives: a serialised model plus a
sample input, which is all `deploy_and_test.py` needs to infer the schema.

    python scripts/train_sklearn.py
"""

import argparse
import json
from pathlib import Path

import joblib
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="artifacts/iris-sk", type=Path)
    args = ap.parse_args()

    X, y = load_iris(return_X_y=True)
    model = RandomForestClassifier(n_estimators=10).fit(X, y)

    args.out.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, args.out / "model.joblib")
    (args.out / "sample_input.json").write_text(json.dumps(X[:5].tolist(), indent=2))
    (args.out / "meta.json").write_text(json.dumps({"framework": "sklearn"}, indent=2))

    print(f"handoff ready: {args.out}")
    print(f"  next: python scripts/deploy_and_test.py --artifact {args.out} --server fastapi")


if __name__ == "__main__":
    main()
