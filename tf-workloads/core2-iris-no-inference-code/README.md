# Iris on TrueFoundry — no inference code

No hand-written `predict`. `tfy deploy-init` generates the server from the registered
model; you build and push the image, TrueFoundry never builds.
Tenant `platform-admin.live-demo.truefoundry.cloud`, ML repo `cx-team`.

Run from this folder. No env vars — `tfy login` + `docker login`.

## 1. Build artifacts

```bash
python scripts/train.py
```

Both frameworks → `artifacts/iris-sk/`, `artifacts/iris-xgb/`.

## 2. Deploy

Logs the model, generates the server, builds, pushes, deploys, smoke-tests.

| | | |
| --- | --- | --- |
| sklearn | FastAPI | `python scripts/deploy.py --artifact artifacts/iris-sk --runtime fastapi` |
| xgboost | FastAPI | `python scripts/deploy.py --artifact artifacts/iris-xgb --runtime fastapi` |
| sklearn | Triton | `~/work/.venvs/tfy-triton-py312/bin/python scripts/deploy.py --artifact artifacts/iris-sk --runtime triton` |
| xgboost | Triton | `~/work/.venvs/tfy-triton-py312/bin/python scripts/deploy.py --artifact artifacts/iris-xgb --runtime triton` |
| sklearn | MLServer | `notebooks/iris_sklearn_mlserver.ipynb` |
| xgboost | MLServer | `notebooks/iris_xgboost_mlserver.ipynb` |

Triton needs the 3.12 interpreter — the control plane rejects models logged from
Python > 3.12. MLServer needs `mlserver build` instead of `docker build`, so it has no
script path.

## 3. Load test

| | | |
| --- | --- | --- |
| sklearn | FastAPI | `python scripts/loadtest.py --artifact artifacts/iris-sk --runtime fastapi -u 20 -t 60s` |
| xgboost | FastAPI | `python scripts/loadtest.py --artifact artifacts/iris-xgb --runtime fastapi -u 20 -t 60s` |
| sklearn | Triton | `python scripts/loadtest.py --artifact artifacts/iris-sk --runtime triton -u 20 -t 60s` |
| xgboost | Triton | `python scripts/loadtest.py --artifact artifacts/iris-xgb --runtime triton -u 20 -t 60s` |

`--web` for the locust UI. CSVs in `loadtest-results/`.

## 4. Teardown

Service only — model versions and images stay.

| | | |
| --- | --- | --- |
| sklearn | FastAPI | `python scripts/teardown.py --artifact artifacts/iris-sk --runtime fastapi` |
| xgboost | FastAPI | `python scripts/teardown.py --artifact artifacts/iris-xgb --runtime fastapi` |
| sklearn | Triton | `python scripts/teardown.py --artifact artifacts/iris-sk --runtime triton` |
| xgboost | Triton | `python scripts/teardown.py --artifact artifacts/iris-xgb --runtime triton` |

## Files

| | |
| --- | --- |
| `train.py` · `deploy.py` · `loadtest.py` · `teardown.py` | steps 1–4. Tenant constants live in `deploy.py` |
| `locustfile.py` | load profile, loaded by `locust -f` |
| `artifacts/<name>/deployed-<runtime>.json` | written by step 2, read by steps 3–4 |
| `notebooks/` | same flow, one per framework × runtime, including MLServer |

Framework is named once, in `meta.json`. Nothing after that branches on it.

## Gotchas

- Triton: Python ≤ 3.12 only. Cold start is 60–90s of silent logs, then `Serving model with Triton` — not a hang
- Triton `/v2/health/ready` lies → poll `/v2/models/<name>/ready`
- `tfy` not on kernel PATH → `!{sys.executable} -m truefoundry.cli ...`
- `!` swallows exits → `assert _exit_code == 0`
- schema inference needs a typed numpy array, not a list of lists
- XGBoost: `predict` only; needs [mlfoundry-server#1196](https://github.com/truefoundry/mlfoundry-server/pull/1196)
- payloads: FastAPI `{"input_0":[[...]]}` · Triton nested `data`, `input_0` · MLServer flat `data`, `predict`
- UI can show `Error` + 0 pods while the service serves 200s — `activeVersion` stuck at 0, rollout never marked terminal. Data plane is right
- tag is always `1` and is overwritten in place, so nothing needs deleting first. But a node that already pulled `:1` won't re-pull — use `--tag 2` if you must know which build answered
- deleting a service 409s if a rollout never finished — cancel `last_deployment_id`, not `.deployment.id`
- notebook cleanup cells are **live** — they delete the service
