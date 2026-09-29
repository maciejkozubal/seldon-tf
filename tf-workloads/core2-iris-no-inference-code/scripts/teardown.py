"""Delete the service. Model versions and images are left alone.

    python scripts/teardown.py --artifact artifacts/iris-sk --runtime fastapi
"""

import argparse
import json
import shutil
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--artifact", type=Path, required=True)
    # Not a fixed choice list: a worker variant is its own deployment, e.g. fastapi-4w.
    ap.add_argument("--runtime", required=True, help="fastapi, triton, fastapi-4w, ...")
    args = ap.parse_args()

    artifact = args.artifact.resolve()
    f = artifact / f"deployed-{args.runtime}.json"
    if not f.is_file():
        have = [p.stem[len("deployed-"):] for p in sorted(artifact.glob("deployed-*.json"))]
        raise SystemExit(f"no {f.name} in {artifact}"
                         f"\n  deployed: {', '.join(have) or 'nothing'}")
    dep = json.loads(f.read_text())

    from truefoundry.common.session import Session
    from truefoundry_sdk import TrueFoundry

    tfy = TrueFoundry(base_url=dep["tfy_host"], api_key=Session.new().access_token)
    # Tenant comes from the file, so an overridden deploy tears down correctly.
    for app in tfy.applications.list(workspace_fqn=dep.get("ws_fqn", "tfy-azure:seldon-tf")):
        if tfy.applications.get(id=app.id).data.name != dep["svc"]:
            continue
        try:
            tfy.applications.delete(id=app.id)
        except Exception:
            # An unfinished rollout blocks the delete with 409. Cancel
            # last_deployment_id — .deployment.id is the *active* version.
            tfy.applications.cancel_deployment(
                id=app.id,
                deployment_id=tfy.applications.get(id=app.id).data.last_deployment_id)
            tfy.applications.delete(id=app.id)
        print(f"deleted {dep['svc']}")
        break
    else:
        print(f"no service {dep['svc']}")

    shutil.rmtree(artifact.parent / dep["svc"], ignore_errors=True)
    f.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
