"""Data scientist side. Plain sklearn / XGBoost — no TrueFoundry import anywhere.

Produces the handoff folder the MLOps engineer receives: a serialised model plus a
sample input, which is all `deploy.py` needs to infer the schema.

    python scripts/train.py                        # both frameworks
    python scripts/train.py --framework sklearn    # just one
"""

import argparse
import json
from pathlib import Path

import joblib
from sklearn.datasets import load_iris

DEFAULT_OUT = {"sklearn": "artifacts/iris-sk", "xgboost": "artifacts/iris-xgb"}


def build_model(framework: str):
    if framework == "sklearn":
        from sklearn.ensemble import RandomForestClassifier

        return RandomForestClassifier(n_estimators=10)
    from xgboost import XGBClassifier

    return XGBClassifier(n_estimators=10)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--framework", choices=sorted(DEFAULT_OUT),
                    help="default: build both")
    args = ap.parse_args()

    X, y = load_iris(return_X_y=True)
    for framework in [args.framework] if args.framework else sorted(DEFAULT_OUT):
        out = Path(DEFAULT_OUT[framework])
        model = build_model(framework).fit(X, y)

        # Named after the case, not a generic model.joblib — readable in the registry
        # and in the generated server.py. deploy.py reads it back off meta.json.
        model_file = f"{out.name}.joblib"

        out.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, out / model_file)
        (out / "sample_input.json").write_text(json.dumps(X[:5].tolist(), indent=2))
        (out / "meta.json").write_text(json.dumps(
            {"framework": framework, "model_file": model_file}, indent=2))
        print(f"handoff ready: {out}  ({framework})")


if __name__ == "__main__":
    main()
