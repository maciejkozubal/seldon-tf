# ML Model deployment on TrueFoundry without inference code

- No hand-written `predict`, `tfy deploy-init` auto generates the server from the registered
model
- You build and push the image, TrueFoundry never builds
- Run from this folder, run `tfy login` + `docker login`
- Tenant `platform-admin.live-demo.truefoundry.cloud`, ML repo `cx-team`


---

## Steps
### 1. Build artifacts

```bash
python scripts/train.py
```

Both frameworks → `artifacts/iris-sk/`, `artifacts/iris-xgb/`.

### 2 Deploy

Logs the model, generates the server, builds, pushes, deploys, smoke-tests.

| | | |
| --- | --- | --- |
| sklearn | FastAPI | `python scripts/deploy.py --artifact artifacts/iris-sk --runtime fastapi` |
| xgboost | FastAPI | `python scripts/deploy.py --artifact artifacts/iris-xgb --runtime fastapi` |
| sklearn | Triton | `~/work/.venvs/tfy-triton-py312/bin/python scripts/deploy.py --artifact artifacts/iris-sk --runtime triton` |
| xgboost | Triton | `~/work/.venvs/tfy-triton-py312/bin/python scripts/deploy.py --artifact artifacts/iris-xgb --runtime triton` |
| sklearn | MLServer | `notebooks/iris_sklearn_mlserver.ipynb` |
| xgboost | MLServer | `notebooks/iris_xgboost_mlserver.ipynb` |

- Triton needs the 3.12 interpreter — the control plane rejects models logged from
Python > 3.12. MLServer needs `mlserver build` instead of `docker build`, so it has no
script path
- `--workers N` is the FastAPI answer to MLServer's `parallel_workers`, it becomes
`uvicorn --workers N`. Defaults are `--workers 1 --cpu 0.5 --memory 1000`
- a `--workers N` run is its own service `<name>-fastapi-Nw-svc`, so it can be
load-tested next to the 1-worker one — give both the same `--cpu` or the comparison
means nothing

```bash
python scripts/deploy.py --artifact artifacts/iris-sk --runtime fastapi --cpu 2
python scripts/deploy.py --artifact artifacts/iris-sk --runtime fastapi --cpu 2 --workers 4
```

### 3 Load test

One command per framework, every deployed runtime, p50 / p99 / success rate side by side

| | |
| --- | --- |
| sklearn | `python scripts/loadtest.py --artifact artifacts/iris-sk` |
| xgboost | `python scripts/loadtest.py --artifact artifacts/iris-xgb` |

- rows come from `deployed-*.json`, so a `--workers 4` service shows up as its own
`fastapi-4w` row next to `fastapi`
- defaults `-u 20 -t 60s`, add `--only triton` for just one, CSVs in `loadtest-results/`
- to find the breaking point raise users until `ok %` drops — `-u 100`, `-u 300`, `-u 1000` — but expect all three to fail together: they share 1 replica at 0.5 CPU, and Triton's edge is dynamic batching and GPU, neither of which a 4-feature iris model on CPU uses
- `wait_time = constant_throughput(1)` in `locustfile.py` caps each user at 1 rps, so users ≈ rps; delete that line for a true throughput ceiling

### (4. Teardown)

- tear down: Service
- leave: model in ML Registry and docker images 

| | | |
| --- | --- | --- |
| sklearn | FastAPI | `python scripts/teardown.py --artifact artifacts/iris-sk --runtime fastapi` |
| xgboost | FastAPI | `python scripts/teardown.py --artifact artifacts/iris-xgb --runtime fastapi` |
| sklearn | Triton | `python scripts/teardown.py --artifact artifacts/iris-sk --runtime triton` |
| xgboost | Triton | `python scripts/teardown.py --artifact artifacts/iris-xgb --runtime triton` |

- `--runtime` here is the variant, so a 4-worker service is `--runtime fastapi-4w`. A
wrong one lists what is deployed

---

## Overrides

Only for **xgboost**, which needs devtest until live-demo picks up [#1196](https://github.com/truefoundry/mlfoundry-server/pull/1196). sklearn stays on live-demo with no flags

Log in first, `deploy.py` refuses if the logged-in host does not match

```bash
tfy login --host https://internal.devtest.truefoundry.tech --relogin
```

```bash
python scripts/deploy.py --artifact artifacts/iris-xgb --runtime fastapi \
  --tfy-host https://internal.devtest.truefoundry.tech \
  --ml-repo default \
  --ws-fqn tfy-usea1-devtest:seldon-tf \
  --domain tfy-usea1-ctl.devtest.truefoundry.tech
```

```bash
~/work/.venvs/tfy-triton-py312/bin/python scripts/deploy.py --artifact artifacts/iris-xgb --runtime triton \
  --tfy-host https://internal.devtest.truefoundry.tech \
  --ml-repo default \
  --ws-fqn tfy-usea1-devtest:seldon-tf \
  --domain tfy-usea1-ctl.devtest.truefoundry.tech
```

- pass all four together, they are not independent, and `--docker-user` as well if the image does not go to `mkozubal`
- `loadtest.py` and `teardown.py` take no overrides, they read the tenant back from `deployed-<variant>.json`
- notebooks have no overrides, edit cell 4 and log in to the matching host
- the login is global, so a sklearn notebook run after this fails with `ML Repo cx-team not found` until you log back in to live-demo

---

## Info

- Triton: Python ≤ 3.12 only. Cold start is 60–90s of silent logs, then `Serving model with Triton` 
- Triton `/v2/health/ready` not actual → poll `/v2/models/<name>/ready`
- `tfy` not on kernel PATH → `!{sys.executable} -m truefoundry.cli ...`
- schema inference needs a typed numpy array, not a list of lists
- XGBoost: `predict` only; needs [mlfoundry-server#1196](https://github.com/truefoundry/mlfoundry-server/pull/1196)
- payloads: FastAPI `{"input_0":[[...]]}` · Triton nested `data`, `input_0` · MLServer flat `data`, `predict`
- MLServer concurrency carries over: `parallel_workers` → `--workers`, adaptive batching →
Triton dynamic batching, more capacity → replicas and autoscaling. The generated `predict`
is sync, so FastAPI already threadpools it and sklearn/XGBoost release the GIL in C
- image tag = model version, so it bumps every run. Reusing a tag does not work: a node that already pulled it never pulls again (non-`latest` = `IfNotPresent`) and keeps serving the old build. Notebooks pin `:1`, so bump theirs by hand after a rebuild

### Files

| | |
| --- | --- |
| `train.py` · `deploy.py` · `loadtest.py` · `teardown.py` | steps 1–4. Tenant constants live in `deploy.py` |
| `locustfile.py` | load profile, loaded by `locust -f` |
| `artifacts/<name>/deployed-<variant>.json` | written by step 2, read by steps 3–4. One per live service |
| `notebooks/` | same flow, one per framework × runtime, including MLServer |

- framework is named once, in `meta.json`. Nothing after that branches on it
