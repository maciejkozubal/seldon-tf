# Iris on TrueFoundry — no inference code

No hand-written `predict`. You build and push the image; TrueFoundry never builds.

## Layout

| Path | |
| --- | --- |
| `notebooks/` | one per model × server |
| `scripts/` | same flow, two roles |
| `artifacts/` | handoff folders (gitignored) |

## Flow

```bash
python scripts/train_sklearn.py                                  # DS
python scripts/build.py    --artifact artifacts/iris-sk          # MLOps
python scripts/deploy.py   --artifact artifacts/iris-sk
python scripts/loadtest.py --artifact artifacts/iris-sk -u 20 -t 60s
python scripts/teardown.py --name iris-sk-fastapi
```

- `train_*.py` — no `truefoundry` import; writes `<folder>.joblib`, `sample_input.json`, `meta.json`
- `build.py` — log → deploy-init → docker build → push; writes `build.json`
- `deploy.py` — deploy → wait → smoke. Reads `build.json`, never opens the model
- `loadtest.py` — locust, re-runnable on its own. `--web` for the UI
- `artifacts/<name>/` — the whole handoff contract, `meta.json` + `build.json`
- framework named only in `meta.json`; nothing downstream branches on it

## Notebooks

| | Server | Kernel | Port |
| --- | --- | --- | --- |
| `iris_sklearn_fastapi` | FastAPI codegen | 3.14 | 8000 |
| `iris_xgboost_fastapi` | FastAPI codegen | 3.14 | 8000 |
| `iris_sklearn_triton` | Triton | 3.12 | 8000 |
| `iris_xgboost_triton` | Triton | 3.12 | 8000 |
| `iris_sklearn_mlserver` | MLServer | 3.12 | 8080 |
| `iris_xgboost_mlserver` | MLServer | 3.12 | 8080 |

Hand-maintained, no generator. Cleanup cells are **live**, but only remove local files
and images — service and model version are updated in place on re-run.

## Gotchas

- Triton: Python ≤ 3.12 only — `400 Python version 3.14 is not supported`. Use `~/work/.venvs/tfy-triton-py312/bin/python`
- `tfy` not on kernel PATH → `!{sys.executable} -m truefoundry.cli ...`
- `!` swallows exits → `assert _exit_code == 0`
- schema inference needs a typed numpy array, not a list of lists
- XGBoost: `predict` only; needs [mlfoundry-server#1196](https://github.com/truefoundry/mlfoundry-server/pull/1196)
- Triton `/v2/health/ready` lies → poll `/v2/models/<name>/ready`
- payloads: FastAPI `{"input_0":[[...]]}` · Triton nested `data`, `input_0` · MLServer flat `data`, `predict`

- tag is always `1`, so **delete the image before re-running** — local *and* Docker Hub.
  A node that already pulled `:1` never re-pulls it (non-`latest` → `IfNotPresent`), so a
  stale Hub copy gets served and `server.py` looks for the wrong model filename.
  `teardown.py --purge-hub` does both, needs `$DOCKERHUB_PAT`

## Open

- MLServer notebook-only (`mlserver build`, not `docker build`)
