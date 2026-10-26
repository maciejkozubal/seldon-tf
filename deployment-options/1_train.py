"""1. Train -> 1_train/model.joblib. Plain sklearn, no TrueFoundry import."""
import joblib, numpy as np
from pathlib import Path
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier

from _env import env

X, y = load_iris(return_X_y=True)
model = RandomForestClassifier(n_estimators=10).fit(X, y)

Path("1_train").mkdir(exist_ok=True)
joblib.dump(model, f"1_train/{env('MODEL_FILE')}")
np.save("1_train/sample.npy", np.asarray(X[:5], np.float32))   # 2A infers the schema from it
print(f"1_train/{env('MODEL_FILE')}")
