"""Compare every runtime a framework is deployed on. Deploys nothing.

    python scripts/loadtest.py --artifact artifacts/iris-sk
    python scripts/loadtest.py --artifact artifacts/iris-xgb -u 20 -t 60s

Every deployed-*.json in the artifact folder is one row, so worker variants show
up next to their runtime. MLServer is deployed from a notebook and writes no
file, so its host is derived from the naming convention and skipped if it does
not answer.
"""

import argparse
import csv
import json
import os
import subprocess
from pathlib import Path

import requests


def targets(artifact: Path):
    """Every deployed variant -> (label, runtime, svc, host)."""
    found = []
    for f in sorted(artifact.glob("deployed-*.json")):
        dep = json.loads(f.read_text())
        found.append((f.stem[len("deployed-"):], dep["runtime"], dep["svc"], dep["host"]))

    # MLServer comes from a notebook, so it has no file. Reuse a sibling's host,
    # swapping the service name and the port.
    if found and not any(r == "mlserver" for _, r, _, _ in found):
        _, _, svc0, host0 = found[0]
        svc = f"{artifact.name}-mlserver-svc"
        found.append(("mlserver", "mlserver", svc,
                      svc + host0.split(svc0, 1)[1].replace("-8000.", "-8080.")))
    return found


def alive(svc: str, host: str, runtime: str) -> bool:
    ready = "/health" if runtime == "fastapi" else f"/v2/models/{svc}/ready"
    try:
        return requests.get(f"https://{host}{ready}", timeout=10).ok
    except requests.RequestException:
        return False


def run_locust(svc: str, host: str, runtime: str, users: int, duration: str, out: Path):
    env = dict(os.environ, TFY_RUNTIME=runtime, TFY_SVC=svc)
    # Locust prints its own tables on stderr; swallow them and keep only the csv.
    p = subprocess.run(
        ["locust", "-f", str(Path(__file__).with_name("locustfile.py")),
         "--host", f"https://{host}", "--csv", str(out / svc), "--headless",
         "-u", str(users), "-r", str(max(1, users // 5)), "-t", duration,
         "--loglevel", "ERROR"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if p.returncode:
        raise SystemExit(p.stderr)

    # The csv is snapshotted on locust's own interval, so the count can miss the
    # last second of requests. Every runtime loses the same tail.
    row = next(r for r in csv.DictReader((out / f"{svc}_stats.csv").open())
               if r["Name"] == "Aggregated")
    reqs, fails = int(row["Request Count"]), int(row["Failure Count"])
    return {"runtime": runtime, "reqs": reqs,
            "ok": 100 * (reqs - fails) / reqs if reqs else 0.0,
            "p50": float(row["50%"]), "p99": float(row["99%"]),
            "rps": float(row["Requests/s"])}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--artifact", type=Path, required=True)
    ap.add_argument("--only", help="one variant, e.g. fastapi, triton, fastapi-4w")
    ap.add_argument("-u", "--users", type=int, default=20)
    ap.add_argument("-t", "--duration", default="60s")
    args = ap.parse_args()

    artifact = args.artifact.resolve()
    out = Path("loadtest-results").resolve()
    out.mkdir(parents=True, exist_ok=True)

    found = [t for t in targets(artifact) if args.only in (None, t[0])]
    if not found:
        raise SystemExit(f"no deployed-*.json in {artifact} — deploy something first")

    rows = []
    for label, runtime, svc, host in found:
        if not alive(svc, host, runtime):
            print(f"{label:11} skip, {host} not answering")
            continue
        print(f"{label:11} {args.duration} at {args.users} users -> {host}", flush=True)
        row = run_locust(svc, host, runtime, args.users, args.duration, out)
        rows.append({**row, "label": label})

    if not rows:
        raise SystemExit("nothing answered — is anything still running?")

    # Same users and duration for every runtime, so the columns are comparable.
    print(f"\n{artifact.name}  {args.users} users  {args.duration}\n")
    print(f"{'runtime':11} {'reqs':>6} {'ok %':>7} {'p50 ms':>7} {'p99 ms':>7} {'rps':>6}")
    for r in rows:
        print(f"{r['label']:11} {r['reqs']:>6} {r['ok']:>7.1f} "
              f"{r['p50']:>7.0f} {r['p99']:>7.0f} {r['rps']:>6.1f}")
    print(f"\ncsv: {out}")


if __name__ == "__main__":
    main()
