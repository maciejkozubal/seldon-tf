"""Inverse of build.py + deploy.py — the `tear-down.sh` of this demo.

    python scripts/teardown.py --name iris-sk-fastapi

Removes the service, the model version, the generated package folder and local
images. Artifact unlinking is asynchronous, so the model-version delete is retried.
"""

import argparse
import subprocess
import time
from pathlib import Path

from common import DOCKER_USER, ML_REPO, WS_FQN as WORKSPACE_FQN


def purge_hub(repo: str, tag: str):
    """Reusing a tag means a node that already pulled it never re-pulls, so the Hub
    copy has to go too or the next deploy can serve the old image."""
    import os

    import requests

    pat = os.environ.get("DOCKERHUB_PAT")
    if not pat:
        print("  set $DOCKERHUB_PAT to purge Docker Hub")
        return
    jwt = requests.post("https://hub.docker.com/v2/users/login/",
                        json={"username": DOCKER_USER, "password": pat},
                        timeout=30).json()["token"]
    r = requests.delete(f"https://hub.docker.com/v2/repositories/{repo}/tags/{tag}/",
                        headers={"Authorization": f"JWT {jwt}"}, timeout=30)
    print(f"  hub delete {repo}:{tag} -> {r.status_code}"
          f"{' (gone)' if r.status_code == 204 else ''}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="base name used at deploy time")
    ap.add_argument("--tag", default="1")
    ap.add_argument("--keep-model", action="store_true")
    ap.add_argument("--keep-images", action="store_true")
    ap.add_argument("--purge-hub", action="store_true",
                    help="also delete the tag on Docker Hub (needs $DOCKERHUB_PAT)")
    ap.add_argument("--max-version", type=int, default=20,
                    help="highest model version to look for when cleaning up")
    args = ap.parse_args()

    from truefoundry.common.session import Session
    from truefoundry.ml import get_client
    from truefoundry_sdk import TrueFoundry

    svc = f"{args.name}-svc"
    tfy = TrueFoundry(base_url=TFY_HOST, api_key=Session.new().access_token)

    for app in tfy.applications.list(workspace_fqn=WORKSPACE_FQN):
        if app.name == svc:
            # A rollout that never finished blocks the delete with 409
            # DEPLOYMENT_IN_PROGRESS, so cancel it first.
            try:
                tfy.applications.delete(id=app.id)
            except Exception:
                tfy.applications.cancel_deployment(
                    id=app.id, deployment_id=tfy.applications.get(id=app.id).data.deployment.id)
                tfy.applications.delete(id=app.id)
            print(f"deleted service {svc}")
            break
    else:
        print(f"no service {svc}")

    if not args.keep_model:
        client = get_client()
        fqn = f"model:truefoundry/{ML_REPO}/{args.name}"
        # Every deploy_and_test.py run logs a new version, so clean up all of them,
        # not just :1.
        for version in range(1, args.max_version + 1):
            for attempt in range(6):
                try:
                    mv = client.get_model_version_by_fqn(f"{fqn}:{version}")
                except Exception:
                    break  # no such version
                try:
                    mv.delete()
                    print(f"deleted model version {fqn}:{version}")
                    break
                except Exception as e:
                    # The app delete unlinks artifacts asynchronously.
                    if attempt == 5:
                        print(f"could not delete {fqn}:{version} — re-run in a minute\n  {e}")
                    else:
                        time.sleep(10)

    repo = f"{DOCKER_USER}/{svc}"
    if not args.keep_images:
        subprocess.run(["docker", "rmi", "-f", f"{repo}:{args.tag}"],
                       check=False, capture_output=True)
        print(f"removed local image {repo}:{args.tag}")
        if args.purge_hub:
            purge_hub(repo, args.tag)
        else:
            print(f"  Docker Hub still has {repo}:{args.tag} — --purge-hub to delete it")

    for base in (Path("artifacts"), Path(".")):
        pkg = base / svc
        if pkg.is_dir():
            subprocess.run(["rm", "-rf", str(pkg)], check=False)
            print(f"removed {pkg}")


if __name__ == "__main__":
    main()
