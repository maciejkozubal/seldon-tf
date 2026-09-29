"""Log the model, generate the server, build and push the image. Nothing is deployed.

    python scripts/train_xgboost.py
    python scripts/build.py --artifact artifacts/iris-xgb --server fastapi

Writes build.json into the artifact folder — the fqn, image and host that deploy.py
and loadtest.py read back.

The tag is reused, so teardown.py has to drop the Docker Hub copy too: a node that
already pulled `:1` will not re-pull it, and would keep serving the old image.

Triton note: the model version records *this* interpreter's Python version, and the
control plane rejects anything above 3.12 for Triton. Run the Triton case with the
3.12 venv:

    ~/work/.venvs/tfy-triton-py312/bin/python scripts/build.py \\
        --artifact artifacts/iris-sk --server triton
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

from common import (DOCKER_USER, ML_REPO, PORTS, WS_FQN, host_for, write_build)

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

    meta = json.loads((artifact / "meta.json").read_text())
    framework_name = meta["framework"]
    # Older handoff folders predate meta.json carrying the filename.
    model_file = meta.get("model_file", "model.joblib")
    model = joblib.load(artifact / model_file)
    # Must be a typed array: schema inference off a plain list of lists fails with
    # "Failed to get numpy types as some of the inputs types are not DataType".
    X = np.asarray(json.loads((artifact / "sample_input.json").read_text()), dtype=np.float32)

    if framework_name == "sklearn":
        from truefoundry.ml import SklearnFramework, sklearn_infer_schema

        framework = SklearnFramework(
            model_filepath=model_file,
            serialization_format="joblib",
            model_schema=sklearn_infer_schema(
                model_input=X, model=model, infer_method_name="predict"
            ),
        )
    elif framework_name == "xgboost":
        from truefoundry.ml import XGBoostFramework, xgboost_infer_schema

        # XGBoost supports only `predict`, so no infer_method_name.
        framework = XGBoostFramework(
            model_filepath=model_file,
            serialization_format="joblib",
            model_schema=xgboost_infer_schema(model_input=X, model=model),
        )
    else:
        raise SystemExit(f"unknown framework in meta.json: {framework_name}")

    fqn = get_client().log_model(
        ml_repo=ML_REPO,
        name=name,
        model_file_or_folder=str(artifact / model_file),
        framework=framework,
    ).fqn
    print(f"logged {fqn}")
    return fqn


def package(fqn: str, svc: str, server: str, workdir: Path) -> Path:
    """`tfy deploy-init` reads the framework back off the registry, so from here on
    nothing in this script cares whether it is sklearn or XGBoost — including the
    model filename, which it bakes into the generated server.py."""
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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--artifact", type=Path, required=True,
                    help="handoff folder from a train_*.py script")
    ap.add_argument("--server", choices=sorted(PORTS), default="fastapi")
    ap.add_argument("--name", help="model + service base name (default: artifact folder name)")
    ap.add_argument("--tag", default="1")
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

    fqn = log_model(artifact, name)
    pkg = package(fqn, svc, args.server, artifact.parent)
    build_and_push(pkg, image, args.server, port)

    path = write_build(artifact, name=name, svc=svc, server=args.server, port=port,
                       host=host_for(svc, port), image=image, fqn=fqn,
                       built_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    print(f"\nwrote {path}")
    print(f"  next: python scripts/deploy.py --artifact {args.artifact}")


if __name__ == "__main__":
    main()
