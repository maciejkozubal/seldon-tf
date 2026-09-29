"""Run locust against a deployed service. Re-runnable — it deploys nothing.

    python scripts/loadtest.py --artifact artifacts/iris-xgb -u 20 -t 60s

Reads build.json for the host and server flavour, so the same command works against
any of them. Results land in loadtest-results/<svc>_stats.csv.
"""

import argparse
import os
import subprocess
from pathlib import Path

from common import read_build


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--artifact", type=Path, required=True)
    ap.add_argument("-u", "--users", type=int, default=10)
    ap.add_argument("-t", "--duration", default="30s")
    ap.add_argument("--out", type=Path, help="csv folder (default: ./loadtest-results)")
    ap.add_argument("--web", action="store_true", help="locust UI instead of headless")
    args = ap.parse_args()

    build = read_build(args.artifact.resolve())
    out = (args.out or Path("loadtest-results")).resolve()
    out.mkdir(parents=True, exist_ok=True)

    # Locust has no clean way to take custom CLI args, so the flavour goes via env.
    env = dict(os.environ, TFY_SERVER=build["server"], TFY_SVC=build["svc"])
    cmd = ["locust", "-f", str(Path(__file__).with_name("locustfile.py")),
           "--host", f"https://{build['host']}",
           "--csv", str(out / build["svc"])]
    if args.web:
        print(f"locust UI: http://localhost:8089 -> https://{build['host']}")
    else:
        cmd += ["--headless", "-u", str(args.users), "-r", str(max(1, args.users // 5)),
                "-t", args.duration, "--only-summary"]

    print(f"\n$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True, env=env)
    if not args.web:
        print(f"\ncsv: {out / build['svc']}_stats.csv")


if __name__ == "__main__":
    main()
