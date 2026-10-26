# Deployment options: decisions, prereqs, caveats

Working notes behind the scripts. `README.md` is how to run them.

## Approach

- `DEPLOYMENT = MODEL x IMAGE x SURFACE`, three independent axes, one script per option.
- Numbered scripts, each printing `1. <did this>` / `2. <proof>`, so the output of one
  step is visibly the input of the next (`MODEL_FQN`, `IMAGE_DIGEST`, `GIT_REF`).
- Those three are written back into `.env` by the script that produces them, so nothing
  is pasted by hand and the UI path can pick up the same values.
- `serving/` is checked-in source, not generated. Only `1_train/` and `serving/model/`
  appear at runtime.
- Baking is not a step: it changes the build context, so it is a `bake` flag on step 3.
  Step 3 owns `serving/model/` (writes it on bake, removes it otherwise) and step 4 reads
  it to decide whether to attach `artifacts_download`.
- Model names encode how they got registered, not where they live: `iris-upload-sdk`,
  `iris-blob-sdk`. Room for `-rest`, `-ui` later.

## Prereqs

| Step | Needs |
| - | - |
| 1 train | `pip install -r requirements-dev.txt`. Writes `model.joblib` **and** `sample.npy`: 2.1 infers the schema from the sample, and no schema means no Deploy button and no codegen. |
| 2.2.1 upload | `TFY_HOST` + `TFY_API_KEY` in `.env`. |
| 2.2.2 blob | Also `azure-storage-blob`, `AZURE_STORAGE_CONNECTION_STRING`, and `REPO_ROOT` matching the ML repo. |
| 3.1 docker | `docker login`, plus a running daemon (`colima start` here). `IMAGE` set in `.env`. |
| 3.2 git | `GIT_LOCAL` pointing at the clone, `gh` auth for the push. Private repo needs a Git integration. |
| 3.3 laptop | Nothing. Step 4 uploads `serving/`. |
| 4 deploy | Matching arg: `docker` \| `git` \| `local`. |

## Caveats

- **Blob pointer URI** must sit inside the ML repo's own artifact root
  (`<integration root>/mlfoundry/<repo>_<repo id>`), not merely inside the storage
  integration. Anything else returns `400 Invalid source URI`. `REPO_ROOT` hardcodes the
  repo id, so it does not port to another tenant.
  - This blunts the point of a pointer: you cannot register artifacts where your pipeline
    already writes them, you must first move them into TrueFoundry's tree. Worth raising.
  - A July 2026 script registered a URI outside that root successfully, so the check
    appears to have tightened. Unverified.
- **Python version.** `serving/requirements.txt` pins `numpy==2.5.3`, which needs Python
  >= 3.12, so the Dockerfile and the buildpack are both on 3.12. The laptop venv is on
  3.14, so image and laptop are not identical; sklearn skew can change predictions.
- **`mv._model_version.artifact_storage_root`** in 2.2.1 is a private attribute and can
  break on an SDK upgrade. Only the step-1 proof line depends on it.
- **`4.2_git.sh`** rsyncs into the repo folder, which *is* `serving/` now that
  `GIT_BUILD_CONTEXT` points here. It guards against copying onto itself, and `--delete`
  was removed after it emptied `serving/` once. Stale files in the repo are not pruned.
- **`.gitignore` excludes `serving/model/`**, so `./4.2_git.sh bake` pushes a build context
  without the model. Needs a carve-out if that combination is ever demoed.
- **`serving/` provenance.** `server.py` is `tfy deploy-init` output from an earlier run
  (I removed an unused pandas import and made `MODEL_PATH` fall back to `model/`).
  `Dockerfile` I wrote by hand: deploy-init emits none.
- **Codegen is server-side, so it is not CLI-only.** `tfy deploy-init model` wraps
  `client._initialize_model_server(...)`, which POSTs to
  `/api/2.0/mlflow/mlfoundry-artifacts/model-versions/export-deployment-files-by-fqn`
  with `{model_version_fqn, workspace_fqn, service_name, model_server}` and unzips the
  response. So SDK and REST can both generate `server.py`; the SDK method is private
  (leading underscore), and REST needs the unzip done by hand.
- **`3.2_generate_serving.sh`** needs a schema, so it only works off 2.2.1. Untested.
- **Secrets.** The Azure key lives in `.env` and has been pasted into chat; rotate it.

## Open

- REST and `tfy` CLI variants of step 2.2.
- Decide whether codegen gets its own numbered step, now that SDK and REST can both do it.
- UI path and screenshots.
- Derive `REPO_ROOT` from the ML repo API instead of hardcoding the id.
- Rename `4.1/4.2/4.3` to `4.1/4.2/4.3` for consistency with 2.1.x.
- Untested end to end: 3.1, 3.2, codegen, and every step 4 variant.
