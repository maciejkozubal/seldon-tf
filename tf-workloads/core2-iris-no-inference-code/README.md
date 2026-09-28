# Iris on TrueFoundry — no inference code

Deploy a model on TrueFoundry **without writing any inference code**, and with
**TrueFoundry never building the image**. You build and push your own image; the platform
only logs the model, generates the serving package, and runs the container you pushed.

That second constraint is the point of this demo — it mirrors a customer whose CI already
builds images and who will not hand build rights to the platform.

```
train (data scientist)  →  artifacts/<name>/  →  deploy + load test (MLOps)  →  live service
```

## Layout

| Path | What it is |
| --- | --- |
| `notebooks/` | One notebook per model-server combination, run top to bottom |
| `scripts/` | The same flow as two roles: `train_*.py` (DS) and `deploy_and_test.py` (MLOps) |
| `artifacts/` | Handoff folders produced by `train_*.py` (gitignored) |

## Scripts — the two-role flow

The data scientist never imports `truefoundry`. They run one script and hand over a folder:

```bash
python scripts/train_sklearn.py     # -> artifacts/iris-sk/
python scripts/train_xgboost.py     # -> artifacts/iris-xgb/
```

Each folder holds `model.joblib`, `sample_input.json` and a one-line `meta.json` naming the
framework. That is the whole contract.

The MLOps engineer takes the folder and runs one command. They never open the model and never
write a `predict`:

```bash
python scripts/deploy_and_test.py --artifact artifacts/iris-sk --server fastapi
```

Stages: log model → `tfy deploy-init` → `docker build` → `docker push` → deploy → wait for
ready → smoke test → locust load test. Results land in `loadtest-results/`.

Tear it all down again:

```bash
python scripts/teardown.py --name iris-sk-fastapi
```

`meta.json` is the only place the framework is named. After `log_model`, `deploy-init` reads
the framework back off the registry, so nothing downstream branches on sklearn vs XGBoost.

### Triton needs Python ≤ 3.12

The model version records the *logging* interpreter's Python version and the control plane
rejects anything above 3.12 for Triton with
`400 Python version 3.14 is not supported for Triton deployment`. `deploy_and_test.py`
fails fast on this rather than letting you find out ten minutes later:

```bash
~/work/.venvs/tfy-triton-py312/bin/python scripts/deploy_and_test.py \
    --artifact artifacts/iris-sk --server triton
```

FastAPI has no such limit and runs fine on 3.14.

## Notebooks

Five combinations, each self-contained and each ending with a copy-pasteable `curl`:

| Notebook | Server | Kernel | Port |
| --- | --- | --- | --- |
| `iris_sklearn_fastapi.ipynb` | TrueFoundry FastAPI codegen | Python 3 (3.14) | 8000 |
| `iris_xgboost_fastapi.ipynb` | TrueFoundry FastAPI codegen | Python 3 (3.14) | 8000 |
| `iris_sklearn_triton.ipynb` | Triton (pytriton) | Python 3.12 (TFY Triton) | 8000 |
| `iris_xgboost_triton.ipynb` | Triton (pytriton) | Python 3.12 (TFY Triton) | 8000 |
| `iris_sklearn_mlserver.ipynb` | MLServer | Python 3.12 (TFY MLServer) | 8080 |

Teardown cells are left commented out so a demo run does not delete itself.

The notebooks are hand-maintained — there is no generator. Keep an edit in one of them if it
only applies there; copy it across by hand if it applies to all five.

## Gotchas worth knowing

- **`tfy` is not on the kernel's PATH.** A notebook kernel launches the venv interpreter
  directly, which does not prepend `venv/bin`. Use
  `!{sys.executable} -m truefoundry.cli ...` (`python -m truefoundry` does not work).
- **IPython `!` swallows non-zero exits.** Every shell cell is followed by
  `assert _exit_code == 0`. Without it a failed `deploy-init` surfaces five minutes later as
  a readiness timeout on an image that was never built.
- **Schema inference needs a typed numpy array.** A list of lists gives
  `500 Failed to get numpy types as some of the inputs types are not DataType`.
- **XGBoost supports only `predict`**, so `xgboost_infer_schema` takes no `infer_method_name`.
  XGBoost deployment needs a control plane with
  [mlfoundry-server#1196](https://github.com/truefoundry/mlfoundry-server/pull/1196)
  (merged 2026-09-28); before it, every XGBoost model failed `deploy-init` with
  `Model framework is not supported for deployment`.
- **Triton's `/v2/health/ready` goes green ~10s before the model is loadable.** Poll
  `/v2/models/<name>/ready` instead.
- **Payload shapes differ per server.** FastAPI `{"input_0": [[...]]}`; Triton KServe v2 with
  nested `data` and input name `input_0`; MLServer KServe v2 with *flat* row-major `data` and
  input name `predict`.

## Open questions

- MLServer is notebook-only: it needs `mlserver build`, not a plain `docker build`, so
  `deploy_and_test.py` does not cover it.
- Re-running `deploy_and_test.py` redeploys before load testing — there is no
  "load test what is already live" mode. Deliberate: one script, one story.
