"""Locust against a deployed service. Deploys nothing — re-run it freely.

    python scripts/loadtest.py --artifact artifacts/iris-sk --runtime fastapi -u 20 -t 60s

Reads deployed-<runtime>.json for the host. Results land in
loadtest-results/<svc>_stats.csv.
"""

import argparse
import json
import os
import subprocess
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--artifact", type=Path, required=True)
    ap.add_argument("--runtime", choices=["fastapi", "triton"], required=True)
    ap.add_argument("-u", "--users", type=int, default=10)
    ap.add_argument("-t", "--duration", default="30s")
    ap.add_argument("--web", action="store_true", help="locust UI instead of headless")
    args = ap.parse_args()

    f = args.artifact.resolve() / f"deployed-{args.runtime}.json"
    if not f.is_file():
        raise SystemExit(f"no {f} — run deploy.py --runtime {args.runtime} first")
    dep = json.loads(f.read_text())
    out = Path("loadtest-results").resolve()
    out.mkdir(parents=True, exist_ok=True)

    # Locust takes no custom CLI args, so the runtime goes via env.
    env = dict(os.environ, TFY_RUNTIME=dep["runtime"], TFY_SVC=dep["svc"])
    cmd = ["locust", "-f", str(Path(__file__).with_name("locustfile.py")),
           "--host", f"https://{dep['host']}", "--csv", str(out / dep["svc"])]
    if args.web:
        print(f"locust UI: http://localhost:8089 -> https://{dep['host']}")
    else:
        cmd += ["--headless", "-u", str(args.users), "-r", str(max(1, args.users // 5)),
                "-t", args.duration, "--only-summary"]

    subprocess.run(cmd, check=True, env=env)
    if not args.web:
        print(f"\ncsv: {out / dep['svc']}_stats.csv")


if __name__ == "__main__":
    main()
