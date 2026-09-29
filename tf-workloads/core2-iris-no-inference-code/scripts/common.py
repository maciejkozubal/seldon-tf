"""Tenant constants and the build.json handoff shared by build/deploy/loadtest."""

import json
from pathlib import Path

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

BUILD_FILE = "build.json"


def host_for(svc: str, port: int) -> str:
    return f"{svc}-{WORKSPACE}-{port}.{DOMAIN}"


def write_build(artifact: Path, **fields) -> Path:
    path = artifact / BUILD_FILE
    path.write_text(json.dumps(fields, indent=2) + "\n")
    return path


def read_build(artifact: Path) -> dict:
    path = artifact / BUILD_FILE
    if not path.is_file():
        raise SystemExit(f"no {BUILD_FILE} in {artifact} — run build.py first")
    return json.loads(path.read_text())


def infer_path(server: str, svc: str) -> str:
    return "/infer" if server == "fastapi" else f"/v2/models/{svc}/infer"
