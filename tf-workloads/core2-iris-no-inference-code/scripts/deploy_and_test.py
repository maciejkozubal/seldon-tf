"""MLOps side. One command: artifact folder in, load-tested live service out.

The engineer running this never wrote inference code and never opened the model.
All they have is what the data scientist dropped in `artifacts/<name>/`.

    python scripts/train_sklearn.py
    python scripts/deploy_and_test.py --artifact artifacts/iris-sk --server fastapi

Stages: log -> deploy-init -> build -> push -> deploy -> wait -> smoke -> load test.

Triton note: the model version records *this* interpreter's Python version, and the
control plane rejects anything above 3.12 for Triton. Run the Triton case with the
3.12 venv:

    ~/work/.venvs/tfy-triton-py312/bin/python scripts/deploy_and_test.py \\
        --artifact artifacts/iris-sk --server triton
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import requests

TFY_HOST = "https://internal.devtest.truefoundry.tech"
ML_REPO = "default"
CLUSTER = "tfy-usea1-devtest"
WORKSPACE = "seldon-tf"
DOMAIN = "tfy-usea1-ctl.devtest.truefoundry.tech"
WS_FQN = f"{CLUSTER}:{WORKSPACE}"
DOCKER_USER = "mkozubal"

# FastAPI serves on 8000 and is the only server we write a Dockerfile for; Triton's
# codegen ships its own, and MLServer is notebook-only (it needs `mlserver build`).
PORTS = {"fastapi": 8000, "triton": 8000}

DOCKERFILE = """FROM python:{py}-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "{port}"]
"""


def run(cmd, **kw):
    """Fail loudly. A silently-skipped stage here costs ten minutes downstream."""
    print(f"\n$ {' '.join(str(c) for c in cmd)}", flush=True)
    subprocess.run(cmd, check=True, **kw)


def log_model(artifact: Path, name: str) -> str:
    """The only stage that needs to know what framework the artifact is."""
    from truefoundry.ml import get_client

    framework_name = json.loads((artifact / "meta.json").read_text())["framework"]
    model = joblib.load(artifact / "model.joblib")
    # Must be a typed array: schema inference off a plain list of lists fails with
    # "Failed to get numpy types as some of the inputs types are not DataType".
    X = np.asarray(json.loads((artifact / "sample_input.json").read_text()), dtype=np.float32)

    if framework_name == "sklearn":
        from truefoundry.ml import SklearnFramework, sklearn_infer_schema

        framework = SklearnFramework(
            model_filepath="model.joblib",
            serialization_format="joblib",
            model_schema=sklearn_infer_schema(
                model_input=X, model=model, infer_method_name="predict"
            ),
        )
    elif framework_name == "xgboost":
        from truefoundry.ml import XGBoostFramework, xgboost_infer_schema

        # XGBoost supports only `predict`, so no infer_method_name.
        framework = XGBoostFramework(
            model_filepath="model.joblib",
            serialization_format="joblib",
            model_schema=xgboost_infer_schema(model_input=X, model=model),
        )
    else:
        raise SystemExit(f"unknown framework in meta.json: {framework_name}")

    fqn = get_client().log_model(
        ml_repo=ML_REPO,
        name=name,
        model_file_or_folder=str(artifact / "model.joblib"),
        framework=framework,
    ).fqn
    print(f"logged {fqn}")
    return fqn


def package(fqn: str, svc: str, server: str, workdir: Path) -> Path:
    """`tfy deploy-init` reads the framework back off the registry, so from here on
    nothing in this script cares whether it is sklearn or XGBoost."""
    out = workdir / svc
    shutil.rmtree(out, ignore_errors=True)
    run([sys.executable, "-m", "truefoundry.cli", "deploy-init", "model",
         "--name", svc, "--model-version-fqn", fqn,
         "--workspace-fqn", WS_FQN, "--model-server", server], cwd=workdir)
    if not out.is_dir():
        raise SystemExit("deploy-init produced nothing")
    print(f"generated: {sorted(p.name for p in out.iterdir())}")
    return out


def build_and_push(pkg: Path, image: str, server: str, port: int):
    if server == "fastapi":
        # The FastAPI codegen emits no Dockerfile (its deploy.py builds on the
        # TrueFoundry builder); we own the image here, so we write one.
        py = f"{sys.version_info.major}.{sys.version_info.minor}"
        (pkg / "Dockerfile").write_text(DOCKERFILE.format(py=py, port=port))

    run(["docker", "build", "--platform", "linux/amd64", "-t", image, str(pkg)])
    run(["docker", "push", image])


def deploy(fqn: str, svc: str, image: str, port: int, host: str):
    from truefoundry.common.session import Session
    from truefoundry_sdk import TrueFoundry

    tfy = TrueFoundry(base_url=TFY_HOST, api_key=Session.new().access_token)
    app = tfy.applications.create_or_update(manifest={
        "name": svc, "type": "service", "workspace_fqn": WS_FQN,
        "image": {"type": "image", "image_uri": image},
        "artifacts_download": {"artifacts": [{
            "type": "truefoundry-artifact", "artifact_version_fqn": fqn,
            "download_path_env_variable": "MODEL_PATH"}]},
        "ports": [{"port": port, "protocol": "TCP", "expose": True,
                   "app_protocol": "http", "host": host}],
        "resources": {"cpu_request": 0.5, "cpu_limit": 0.5,
                      "memory_request": 1000, "memory_limit": 1000,
                      "ephemeral_storage_request": 2000, "ephemeral_storage_limit": 2000},
        "replicas": 1,
    })
    # create_or_update returns a Deployment: `id` is the deployment, not the app.
    print(f"deployed {svc} (application_id {app.data.application_id})")


def wait_ready(host: str, svc: str, server: str, timeout: int):
    # Triton's /v2/health/ready goes green ~10s before pytriton binds the model, so
    # poll the model's own readiness endpoint instead.
    path = "/health" if server == "fastapi" else f"/v2/models/{svc}/ready"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(f"https://{host}{path}", timeout=5).ok:
                print(f"{svc} ready")
                return
        except requests.RequestException:
            pass
        time.sleep(5)
    raise SystemExit(f"{svc} not ready after {timeout}s")


def payload(server: str, rows):
    if server == "fastapi":
        return {"input_0": rows}
    return {"inputs": [{"name": "input_0", "shape": [len(rows), len(rows[0])],
                        "datatype": "FP32", "data": rows}]}


def infer_path(server: str, svc: str) -> str:
    return "/infer" if server == "fastapi" else f"/v2/models/{svc}/infer"


def smoke(host: str, svc: str, server: str, rows):
    url = f"https://{host}{infer_path(server, svc)}"
    r = requests.post(url, json=payload(server, rows), timeout=30)
    print(f"smoke {r.status_code} {r.text}")
    r.raise_for_status()


def load_test(host: str, svc: str, server: str, users: int, duration: str, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TFY_SERVER=server, TFY_SVC=svc)
    run(["locust", "-f", str(Path(__file__).with_name("locustfile.py")),
         "--headless", "-u", str(users), "-r", str(max(1, users // 5)),
         "-t", duration, "--host", f"https://{host}",
         "--csv", str(out / svc), "--only-summary"], env=env)
    print(f"load-test csv: {out / svc}_stats.csv")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--artifact", type=Path, required=True,
                    help="handoff folder from a train_*.py script")
    ap.add_argument("--server", choices=sorted(PORTS), default="fastapi")
    ap.add_argument("--name", help="model + service base name (default: artifact folder name)")
    ap.add_argument("--tag", default="1")
    ap.add_argument("--users", type=int, default=10)
    ap.add_argument("--duration", default="30s")
    ap.add_argument("--ready-timeout", type=int, default=600)
    ap.add_argument("--skip-load-test", action="store_true")
    args = ap.parse_args()

    if args.server == "triton" and sys.version_info >= (3, 13):
        raise SystemExit(
            f"Triton needs a model logged from Python <= 3.12 (running {sys.version.split()[0]}).\n"
            "Re-run with: ~/work/.venvs/tfy-triton-py312/bin/python "
            f"{' '.join(sys.argv)}"
        )

    artifact = args.artifact.resolve()
    if not (artifact / "meta.json").is_file():
        raise SystemExit(f"{artifact} is not a handoff folder — run a train_*.py script first")

    name = args.name or f"{artifact.name}-{args.server}"
    svc = f"{name}-svc"
    image = f"{DOCKER_USER}/{svc}:{args.tag}"
    port = PORTS[args.server]
    host = f"{svc}-{WORKSPACE}-{port}.{DOMAIN}"
    workdir = artifact.parent

    fqn = log_model(artifact, name)
    pkg = package(fqn, svc, args.server, workdir)
    build_and_push(pkg, image, args.server, port)
    deploy(fqn, svc, image, port, host)
    wait_ready(host, svc, args.server, args.ready_timeout)

    rows = json.loads((artifact / "sample_input.json").read_text())
    smoke(host, svc, args.server, rows)

    if not args.skip_load_test:
        load_test(host, svc, args.server, args.users, args.duration,
                  workdir.parent / "loadtest-results")

    print(f"\nlive: https://{host}{infer_path(args.server, svc)}")
    print(f"teardown: python scripts/teardown.py --name {name} --server {args.server}")


if __name__ == "__main__":
    main()
