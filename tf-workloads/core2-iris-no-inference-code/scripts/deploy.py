"""Deploy the image build.py pushed, wait for it, and smoke-test it.

    python scripts/deploy.py --artifact artifacts/iris-xgb

Everything comes from build.json, so this never opens the model and never needs to
know the framework. Load testing is loadtest.py.
"""

import argparse
import json
import time
from pathlib import Path

import requests

from common import TFY_HOST, WS_FQN, infer_path, read_build


def deploy(build: dict):
    from truefoundry.common.session import Session
    from truefoundry_sdk import TrueFoundry

    tfy = TrueFoundry(base_url=TFY_HOST, api_key=Session.new().access_token)
    app = tfy.applications.create_or_update(manifest={
        "name": build["svc"], "type": "service", "workspace_fqn": WS_FQN,
        "image": {"type": "image", "image_uri": build["image"]},
        "artifacts_download": {"artifacts": [{
            "type": "truefoundry-artifact", "artifact_version_fqn": build["fqn"],
            "download_path_env_variable": "MODEL_PATH"}]},
        "ports": [{"port": build["port"], "protocol": "TCP", "expose": True,
                   "app_protocol": "http", "host": build["host"]}],
        "resources": {"cpu_request": 0.5, "cpu_limit": 0.5,
                      "memory_request": 1000, "memory_limit": 1000,
                      "ephemeral_storage_request": 2000, "ephemeral_storage_limit": 2000},
        "replicas": 1,
    })
    # create_or_update returns a Deployment: `id` is the deployment, not the app.
    print(f"deployed {build['svc']} (application_id {app.data.application_id})")


def wait_ready(build: dict, timeout: int):
    # Triton's /v2/health/ready goes green ~10s before pytriton binds the model, so
    # poll the model's own readiness endpoint instead.
    path = "/health" if build["server"] == "fastapi" else f"/v2/models/{build['svc']}/ready"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(f"https://{build['host']}{path}", timeout=5).ok:
                print(f"{build['svc']} ready")
                return
        except requests.RequestException:
            pass
        time.sleep(5)
    raise SystemExit(f"{build['svc']} not ready after {timeout}s")


def payload(server: str, rows):
    if server == "fastapi":
        return {"input_0": rows}
    return {"inputs": [{"name": "input_0", "shape": [len(rows), len(rows[0])],
                        "datatype": "FP32", "data": rows}]}


def smoke(build: dict, rows):
    url = f"https://{build['host']}{infer_path(build['server'], build['svc'])}"
    r = requests.post(url, json=payload(build["server"], rows), timeout=30)
    print(f"smoke {r.status_code} {r.text}")
    r.raise_for_status()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--artifact", type=Path, required=True)
    ap.add_argument("--ready-timeout", type=int, default=600)
    ap.add_argument("--skip-smoke", action="store_true")
    args = ap.parse_args()

    artifact = args.artifact.resolve()
    build = read_build(artifact)
    print(f"image {build['image']}  built {build['built_at']}")

    deploy(build)
    wait_ready(build, args.ready_timeout)

    if not args.skip_smoke:
        smoke(build, json.loads((artifact / "sample_input.json").read_text()))

    print(f"\nlive: https://{build['host']}{infer_path(build['server'], build['svc'])}")
    print(f"  load test: python scripts/loadtest.py --artifact {args.artifact}")
    print(f"  teardown:  python scripts/teardown.py --name {build['name']}")


if __name__ == "__main__":
    main()
