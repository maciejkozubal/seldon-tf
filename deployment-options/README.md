# Deployment options

`DEPLOYMENT = MODEL x IMAGE x SURFACE`. The axes are independent: pick one from each.
Same manifest on every surface. These scripts are the **SDK** surface; UI, CLI and REST
do the same thing.

```
1   Train          -> 1_train/model.joblib + sample.npy
2   Model          where does the model live?
    2.1 Local      baked into the build context    -> 4
    2.2 Registry   -> MODEL_FQN, mounted at runtime -> 5
        2.2.1 uploaded      platform stores the file
        2.2.2 blob          registered in place, no re-upload
3   Serving code   server.py + requirements.txt
    3.1 Your own   serving/, checked in            (no script)
    3.2 Generated  from the model schema           (CLI | SDK, needs 2.2.1)
4   Image          from where to deploy the code?
    4.1 Docker image   image URI, nothing is built
    4.2 Git repo       repo URL + build context
    4.3 Laptop         folder uploaded by CLI/SDK
        4.2/4.3 then pick: Dockerfile | buildpack
5   Deploy         image from 4 + MODEL_FQN from 2.2 (if used)
```

## Files

```
0_teardown.sh              removes services, folders, images, repo folders
.env                       every name and key, gitignored
_env.py                    loads .env, writes MODEL_FQN / GIT_REF / IMAGE_DIGEST back
_bake.sh                   the bake flag, sourced by every step 4
1_train.py                 -> 1_train/
2.2.1_register_upload.py   -> MODEL_FQN as iris-upload-sdk, platform stores the file
2.2.2_register_blob.py     -> MODEL_FQN as iris-blob-sdk, registers a blob in place
serving/                   3.1: your source, checked in
  server.py                reads MODEL_PATH + MODEL_FILE; no model name baked in
  requirements.txt
  Dockerfile               4.1 and 4.2; 4.3 needs neither
  model/                   written by `bake` only
3_generate_serving.sh      step 3 via CLI (tfy deploy-init) + a Dockerfile
4.1_docker.sh  [bake]      build + push $IMAGE
4.2_git.sh     [bake]      push serving/ as serving-with|without-model/
4.3_local.sh   [bake]      nothing to build, step 5 uploads serving/
5_deploy.py                docker | git | local
infer.py                   smoke test
```

Only `1_train/` and `serving/model/` are written at runtime. Step 2.2 produces no local
files: its output is `MODEL_FQN` in `.env`.

## Run

```bash
pip install -r requirements-dev.txt

python 1_train.py

python 2.2.1_register_upload.py    # or 2.2.2_register_blob.py
# ./3_generate_serving.sh       # optional: regenerate serving/ from the schema

./4.1_docker.sh                    # or ./4.2_git.sh, or ./4.3_local.sh
python 5_deploy.py docker          # match step 4: docker | git | local

python infer.py
```

Skip step 2.2 and pass `bake` instead, and the model ships in the image:

```bash
python 1_train.py
./4.3_local.sh bake
python 5_deploy.py local
```

## Notes

- **2A vs bake.** 2A mounts the model at runtime: one image serves any version, swapped
  by changing one FQN, cached across replicas. Bake puts it in the image: a new model
  version means a new build. It is a build-context decision, which is why it lives on
  step 3 rather than being a step of its own.
- Step 3 owns `serving/model/`: `bake` writes it, a plain run removes it. Step 4 reads
  it to decide whether to attach `artifacts_download`, so there is nothing to keep in
  sync by hand.
- **2.2.1 vs 2.2.2** are the same `log_model()` call; only `model_file_or_folder` differs
  (a local path vs a `BlobStorageDirectory`). They register under different names so the
  source is visible in the UI list.
- **2.2.2's `URI`** must sit inside the ML repo's own artifact root (`REPO_ROOT` in
  `.env`), not merely inside the storage integration, or the platform answers "Invalid
  source URI". `REPO_ROOT` carries the repo id, so it is per-tenant.
- **3_generate_serving.sh** is the one-click-from-registry shortcut: `tfy deploy-init` writes
  `server.py` + `requirements.txt` from the model schema, so no inference code is written
  by hand. It only writes files; deploy with `5_deploy.py`. 2a2 registers a pointer with
  no schema, so it has nothing to generate from.
- **3.1** needs `IMAGE` uncommented in `.env` and a `docker login`.
- **3.2** needs `GIT_LOCAL` (path to the local clone); a private repo needs a Git
  integration. The build runs on the cluster, so the first one takes a few minutes.
  The UI form needs two values: the repo URL and the build context path, since
  `serving/` is nested rather than at the repo root. The flag picks the folder:
  `serving-without-model/` (model mounted at runtime) or `serving-with-model/`
  (model baked in), so both options live in the repo side by side.
- **3.3** uploads `serving/` from the laptop, so there is no repo and no registry push.
  SDK and REST cannot do this: they use git or a tarball.
- Changing the model after 2A: re-run the register step and `5_deploy.py`. No rebuild.
  `MODEL_FQN` persists in `.env`, so switching paths is just running the other script.

## TODO

- REST and `tfy` CLI variants of step 2.2, named `iris-upload-rest` etc.
- UI path, screenshots
