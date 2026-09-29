"""Log a model, generate its server, build the image, push it, deploy, smoke-test.

    python scripts/deploy.py --artifact artifacts/iris-sk --runtime fastapi
    ~/work/.venvs/tfy-triton-py312/bin/python \
        scripts/deploy.py --artifact artifacts/iris-sk --runtime triton

No inference code anywhere: `tfy deploy-init` reads the framework back off the
registry and writes server.py. Nothing below branches on sklearn vs xgboost.

Writes deployed.json into the artifact folder for loadtest.py / teardown.py.
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import requests

TFY_HOST = "https://platform-admin.live-demo.truefoundry.cloud"
ML_REPO = "cx-team"
WS_FQN = "tfy-azure:seldon-tf"
DOMAIN = "az-apps.live-demo.truefoundry.cloud"  # per-cluster, not per-tenant
DOCKER_USER = "mkozubal"

DOCKERFILE = """FROM python:{py}-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "{workers}"]
"""


def run(cmd, **kw):
    print(f"\n$ {' '.join(map(str, cmd))}", flush=True)
    subprocess.run(cmd, check=True, **kw)


def log_model(artifact: Path, name: str) -> str:
    """The only step that knows the framework — and it reads it from meta.json."""
    from truefoundry.ml import get_client

    meta = json.loads((artifact / "meta.json").read_text())
    model = joblib.load(artifact / meta["model_file"])
    # Schema inference needs a typed array; a list of lists fails.
    X = np.asarray(json.loads((artifact / "sample_input.json").read_text()), np.float32)

    if meta["framework"] == "sklearn":
        from truefoundry.ml import SklearnFramework, sklearn_infer_schema

        fw = SklearnFramework(model_filepath=meta["model_file"],
                              serialization_format="joblib",
                              model_schema=sklearn_infer_schema(X, model, "predict"))
    else:
        from truefoundry.ml import XGBoostFramework, xgboost_infer_schema

        # XGBoost exposes only `predict`, so no infer_method_name.
        fw = XGBoostFramework(model_filepath=meta["model_file"],
                              serialization_format="joblib",
                              model_schema=xgboost_infer_schema(X, model))

    fqn = get_client().log_model(ml_repo=ML_REPO, name=name, framework=fw,
                                model_file_or_folder=str(artifact / meta["model_file"])).fqn
    print(f"logged {fqn}")
    return fqn


def build_image(fqn: str, svc: str, runtime: str, image: str, workdir: Path,
                workers: int):
    pkg = workdir / svc
    shutil.rmtree(pkg, ignore_errors=True)
    run([sys.executable, "-m", "truefoundry.cli", "deploy-init", "model", "--name", svc,
         "--model-version-fqn", fqn, "--workspace-fqn", WS_FQN, "--model-server", runtime],
        cwd=workdir)
    if runtime == "fastapi":
        # The FastAPI codegen ships no Dockerfile (its own deploy.py uses the
        # TrueFoundry builder); we build the image ourselves, so write one.
        (pkg / "Dockerfile").write_text(DOCKERFILE.format(
            py=f"{sys.version_info.major}.{sys.version_info.minor}", workers=workers))
    run(["docker", "build", "--platform", "linux/amd64", "-t", image, str(pkg)])
    run(["docker", "push", image])


def deploy(svc: str, image: str, fqn: str, host: str, cpu: float, memory: int) -> str:
    from truefoundry.common.session import Session
    from truefoundry_sdk import TrueFoundry

    tfy = TrueFoundry(base_url=TFY_HOST, api_key=Session.new().access_token)
    app = tfy.applications.create_or_update(manifest={
        "name": svc, "type": "service", "workspace_fqn": WS_FQN,
        "image": {"type": "image", "image_uri": image},
        "artifacts_download": {"artifacts": [{"type": "truefoundry-artifact",
            "artifact_version_fqn": fqn, "download_path_env_variable": "MODEL_PATH"}]},
        "ports": [{"port": 8000, "protocol": "TCP", "expose": True,
                   "app_protocol": "http", "host": host}],
        "resources": {"cpu_request": cpu, "cpu_limit": cpu,
                      "memory_request": memory, "memory_limit": memory,
                      "ephemeral_storage_request": 2000, "ephemeral_storage_limit": 2000},
        "replicas": 1,
    })
    return app.data.application_id


def wait_and_smoke(svc: str, runtime: str, host: str, rows, timeout: int):
    # Triton's /v2/health/ready goes green before the model binds, and Triton is
    # silent for ~60-90s while it boots — poll the model's own readiness instead.
    ready = "/health" if runtime == "fastapi" else f"/v2/models/{svc}/ready"
    path = "/infer" if runtime == "fastapi" else f"/v2/models/{svc}/infer"
    body = ({"input_0": rows} if runtime == "fastapi" else
            {"inputs": [{"name": "input_0", "shape": [len(rows), len(rows[0])],
                         "datatype": "FP32", "data": rows}]})

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(f"https://{host}{ready}", timeout=5).ok:
                break
        except requests.RequestException:
            pass
        time.sleep(5)
    else:
        raise SystemExit(f"{svc} not ready after {timeout}s")

    r = requests.post(f"https://{host}{path}", json=body, timeout=30)
    print(f"\nsmoke {r.status_code} {r.text[:200]}")
    r.raise_for_status()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--artifact", type=Path, required=True)
    ap.add_argument("--runtime", choices=["fastapi", "triton"], required=True)
    ap.add_argument("--tag", help="default: the model version, so it bumps every run")
    ap.add_argument("--timeout", type=int, default=900)
    # MLServer's parallel_workers equivalent. Each worker is a process with its
    # own copy of the model, so give it cores and memory to match.
    ap.add_argument("--workers", type=int, default=1, help="uvicorn workers, fastapi only")
    ap.add_argument("--cpu", type=float, default=0.5)
    ap.add_argument("--memory", type=int, default=1000, help="MiB")
    # Escape hatch for a different tenant. Defaults above are live-demo; pass all
    # four together, they are not independent.
    for flag in ("tfy-host", "ml-repo", "ws-fqn", "domain", "docker-user"):
        ap.add_argument(f"--{flag}", help=f"override {flag.replace('-', '_').upper()}")
    args = ap.parse_args()

    for flag in ("tfy_host", "ml_repo", "ws_fqn", "domain", "docker_user"):
        if getattr(args, flag):
            globals()[flag.upper()] = getattr(args, flag)

    from truefoundry.common.session import Session

    if (logged_in := Session.new().tfy_host.rstrip("/")) != TFY_HOST.rstrip("/"):
        # --relogin: a plain `tfy login` only prompts when a session already exists.
        raise SystemExit(f"logged in to {logged_in}, not {TFY_HOST}\n"
                         f"  tfy login --host {TFY_HOST} --relogin")

    if args.runtime == "triton" and sys.version_info >= (3, 13):
        raise SystemExit("Triton needs a model logged from Python <= 3.12. Re-run with:\n"
                         f"  ~/work/.venvs/tfy-triton-py312/bin/python {' '.join(sys.argv)}")

    artifact = args.artifact.resolve()
    if not (artifact / "meta.json").is_file():
        raise SystemExit(f"{artifact} is not a handoff folder — run train.py first")

    if args.workers > 1 and args.runtime != "fastapi":
        raise SystemExit("--workers is fastapi only; Triton has its own instance count")
    if args.workers > args.cpu:
        print(f"note: {args.workers} workers on {args.cpu} cpu — they will contend")

    name = f"{artifact.name}-{args.runtime}"
    # Workers get their own service, so 1w and 4w can be load-tested side by side.
    svc = f"{name}-svc" if args.workers == 1 else f"{name}-{args.workers}w-svc"
    host = f"{svc}-{WS_FQN.split(':')[-1]}-8000.{DOMAIN}"

    fqn = log_model(artifact, name)
    # Tag = model version. A reused tag is never re-pulled by a node that already
    # has it (non-latest => IfNotPresent), so it would keep serving the old build.
    image = f"{DOCKER_USER}/{svc}:{args.tag or fqn.rsplit(':', 1)[-1]}"
    build_image(fqn, svc, args.runtime, image, artifact.parent, args.workers)
    print(f"\ndeployed {svc} "
          f"({deploy(svc, image, fqn, host, args.cpu, args.memory)})")
    wait_and_smoke(svc, args.runtime, host,
                   json.loads((artifact / "sample_input.json").read_text()), args.timeout)

    # One file per variant: fastapi, fastapi-4w and triton can all be live at once.
    variant = svc[len(artifact.name) + 1:-len("-svc")]
    (artifact / f"deployed-{variant}.json").write_text(json.dumps(
        {"svc": svc, "runtime": args.runtime, "host": host, "image": image,
         "fqn": fqn, "workers": args.workers, "cpu": args.cpu,
         "tfy_host": TFY_HOST, "ml_repo": ML_REPO, "ws_fqn": WS_FQN},
        indent=2) + "\n")
    print(f"\nlive: https://{host}"
          f"{'/infer' if args.runtime == 'fastapi' else f'/v2/models/{svc}/infer'}")
    print(f"  load test: python scripts/loadtest.py --artifact {args.artifact}")
    print(f"  teardown:  python scripts/teardown.py --artifact {args.artifact}"
          f" --runtime {variant}")


if __name__ == "__main__":
    main()
