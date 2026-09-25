"""Read one onboarding run's log: what failed, what was flagged, grouped by reason.

Read-only -- it runs a single SELECT through /app/onboarding/query (PHIX-98714).

  python run_log.py --run 1383
  python run_log.py --run 1383 --json                 # for a subagent to parse
  python run_log.py --fein 234223423 --since "2026-09-11 09:59:00"   # find the run
  python run_log.py --run 1376 --csv issues.csv

Credentials: UZIO_ONBOARDING_USERNAME / UZIO_ONBOARDING_PASSWORD, or a JSON file
{"username": ..., "password": ...} at --creds (default ~/.uzio/onboarding-creds.json).
--fein is also the FEIN logged in with; --since is UTC.
"""
import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from utils import onboarding_core as oc
from push_census import DEFAULT_CREDS, die, read_credentials


def creds_fein(path):
    """The FEIN stored next to the credentials, if there is one. Never prints anything."""
    import os
    if os.environ.get("UZIO_ONBOARDING_FEIN"):
        return os.environ["UZIO_ONBOARDING_FEIN"]
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return (data.get("prod", data) or {}).get("fein")


def table(rows, headers, maxw=90):
    if not rows:
        return
    cells = [[str(r.get(h, "")) for h in headers] for r in rows]
    cells = [[c if len(c) <= maxw else c[:maxw - 1] + "~" for c in row] for row in cells]
    width = [max([len(h)] + [len(r[i]) for r in cells]) for i, h in enumerate(headers)]
    line = lambda cs: "  ".join(c.ljust(width[i]) for i, c in enumerate(cs)).rstrip()
    print(line(headers))
    print(line(["-" * w for w in width]))
    for row in cells:
        print(line(row))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", type=int, help="run id (onboarding_automation_history.id)")
    ap.add_argument("--fein", help="find the run instead: the employer pushed to")
    ap.add_argument("--user", help="who pushed (defaults to the login username)")
    ap.add_argument("--since", help="UTC 'YYYY-MM-DD HH:MM:SS' the push started")
    ap.add_argument("--vendor", default="ADP", choices=["ADP", "PAYCOM"], help="for the login only")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--csv", help="write every issue row to this file")
    ap.add_argument("--creds", default=str(DEFAULT_CREDS))
    ap.add_argument("--host", default=oc.DEFAULT_PROD_HOST)
    ap.add_argument("--wait", type=int, default=0, help="seconds to wait for a run still in progress")
    args = ap.parse_args()

    if not args.run and not (args.fein and args.since):
        die(2, "Give --run <id>, or --fein with --since.")

    username, password = read_credentials(args.creds)
    # The token is issued per employer, so a login needs some FEIN even when the run
    # is addressed by id: take it from --fein, else from the credentials file.
    fein_for_login = args.fein or creds_fein(args.creds) or ""
    if not fein_for_login:
        die(2, "Need a FEIN to log in: pass --fein, or add \"fein\" to the credentials file.")
    try:
        token = oc.login(username, password, fein_for_login, args.vendor, prod_host=args.host)
        if args.run:
            row = oc.fetch_run_log(token, args.run, prod_host=args.host, wait_seconds=args.wait)
        else:
            since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
            row = oc.find_run_since(token, args.fein, args.user or username, since, prod_host=args.host)
            if not row:
                out = {"found": False, "fein": args.fein, "since": args.since}
                print(json.dumps(out) if args.json else
                      f"No run for FEIN {args.fein} started by {args.user or username} "
                      f"within 30 minutes of {args.since} UTC.")
                return 1
    except oc.OnboardingAPIError as e:
        die(3, f"{e}")

    errors = oc.run_issues(row.get("error_messages"))
    warnings = oc.run_issues(row.get("optional_validations"))
    out = {
        "found": True, "run_id": row.get("id"),
        "started_ist": oc.ist(row.get("start_time")), "ended_ist": oc.ist(row.get("end_time")),
        "still_running": not row.get("end_time"),
        "errors": len(errors), "warnings": len(warnings),
        "error_groups": oc.group_issues(errors), "warning_groups": oc.group_issues(warnings),
    }
    if args.csv:
        rows = ([{"Severity": "Error", **e} for e in errors]
                + [{"Severity": "Warning", **w} for w in warnings])
        if rows:
            with open(args.csv, "w", encoding="utf-8", newline="") as fh:   # plain UTF-8, no BOM
                writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
            out["issues_csv"] = args.csv

    if args.json:
        print(json.dumps(out, indent=2, default=str))
        return 1 if errors else 0

    print(f"Run {out['run_id']}  |  started {out['started_ist']} IST  |  "
          f"{'STILL RUNNING' if out['still_running'] else 'ended ' + out['ended_ist'] + ' IST'}")
    print(f"{out['errors']} error rows, {out['warnings']} warning rows\n")
    if errors:
        print("ERRORS (records the API skipped), grouped by reason:")
        table(out["error_groups"], ["Employees", "Module", "Reason", "Employee IDs"])
        print()
    if warnings:
        print("WARNINGS (records went through, something was flagged):")
        table(out["warning_groups"], ["Employees", "Module", "Reason", "Employee IDs"])
    if out.get("issues_csv"):
        print(f"\nEvery row: {out['issues_csv']}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
