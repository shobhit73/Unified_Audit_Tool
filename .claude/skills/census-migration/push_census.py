"""Push a corrected census to the Uzio onboarding API and report what it logged.

PRODUCTION. Every run creates or updates real employee records, so the push only
happens when --confirm repeats the FEIN exactly. Without it the script stops.

  python push_census.py --fein 234223423 --vendor ADP \
      --census corrected.csv --mapping job_title_mapping.csv --dry-run
  python push_census.py ... --confirm 234223423

Credentials never come from the command line (they would land in shell history):
  UZIO_ONBOARDING_USERNAME / UZIO_ONBOARDING_PASSWORD, or a JSON file
  {"username": "...", "password": "..."} at --creds (default ~/.uzio/onboarding-creds.json).
Keep that file OUTSIDE this repo.

Exit codes: 0 pushed, no errors logged | 1 pushed, errors logged | 2 usage /
not confirmed | 3 the API or the lookup failed.
"""
import argparse
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from utils import onboarding_core as oc

DEFAULT_CREDS = Path.home() / ".uzio" / "onboarding-creds.json"


def die(code, msg):
    """Stop with a meaningful exit code: 2 usage / not confirmed, 3 API failure."""
    print(msg, file=sys.stderr)
    sys.exit(code)


def read_credentials(path):
    """(username, password) from the environment, else the JSON file. Never printed."""
    user = os.environ.get("UZIO_ONBOARDING_USERNAME")
    password = os.environ.get("UZIO_ONBOARDING_PASSWORD")
    if user and password:
        return user, password
    p = Path(path)
    if not p.exists():
        die(2, f"No credentials. Set UZIO_ONBOARDING_USERNAME / UZIO_ONBOARDING_PASSWORD, "
                 f"or put {{\"username\": ..., \"password\": ...}} in {p}.")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        die(2, f"{p} is not valid JSON: {e}")
    data = data.get("prod", data)
    if not data.get("username") or not data.get("password"):
        die(2, f"{p} needs both a username and a password.")
    return data["username"], data["password"]


def count_rows(path):
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            return max(sum(1 for _ in csv.reader(fh)) - 1, 0)
    except (OSError, UnicodeDecodeError):
        return None


def describe(args, census, mapping, license_file):
    """What this push would send -- printed before every push, dry-run or not."""
    out = {"fein": args.fein, "vendor": args.vendor, "host": args.host,
           "census_file": str(census), "census_employees": count_rows(census),
           "mapping_file": str(mapping), "mapping_rows": count_rows(mapping),
           "license_file": str(license_file) if license_file else None}
    print(json.dumps({"about_to_push": out}, indent=2))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fein", required=True)
    ap.add_argument("--vendor", required=True, choices=["ADP", "PAYCOM"])
    ap.add_argument("--census", required=True, help="corrected census CSV")
    ap.add_argument("--mapping", required=True, help="job title mapping CSV (required by the API)")
    ap.add_argument("--license", help="optional License & Emergency Contact file")
    ap.add_argument("--confirm", help="repeat the FEIN to actually push")
    ap.add_argument("--dry-run", action="store_true", help="show what would be sent and stop")
    ap.add_argument("--creds", default=str(DEFAULT_CREDS))
    ap.add_argument("--host", default=oc.DEFAULT_PROD_HOST)
    ap.add_argument("--out-dir", default=".", help="where the issues CSV is written")
    args = ap.parse_args()

    census, mapping = Path(args.census), Path(args.mapping)
    license_file = Path(args.license) if args.license else None
    for f in [census, mapping] + ([license_file] if license_file else []):
        if not f.exists():
            die(2, f"File not found: {f}")

    describe(args, census, mapping, license_file)
    if args.dry_run:
        print("Dry run: nothing was sent.")
        return 0
    if (args.confirm or "").strip() != args.fein.strip():
        die(2, "Not confirmed. Re-run with --confirm <the same FEIN> once the user has said yes "
                 "to this exact push. This creates or updates real employee records.")

    username, password = read_credentials(args.creds)
    try:
        token = oc.login(username, password, args.fein, args.vendor, prod_host=args.host)
    except oc.OnboardingAPIError as e:
        die(3, f"{e}")

    result = oc.new_result(args.fein, username)
    try:
        resp = oc.push_employee_census(
            token,
            census.read_bytes(), census.name,
            mapping.read_bytes(), mapping.name,
            license_file.read_bytes() if license_file else None,
            license_file.name if license_file else None,
            prod_host=args.host)
        result.update(ok=resp.ok, status=resp.status_code, text=resp.text[:3000],
                      run_id=oc.automation_id(resp))
    except oc.OnboardingAPIError as e:
        # A big census outlasts the request while Uzio keeps processing: the run is
        # found by FEIN + user + start time instead.
        result["push_error"] = str(e)
    if result["run_id"] is not None or oc.lost_answer(result):
        oc.attach_run_log(result, token, prod_host=args.host)

    return report(result, Path(args.out_dir))


def report(result, out_dir):
    row = result.get("run") or {}
    errors = oc.run_issues(row.get("error_messages"))
    warnings = oc.run_issues(row.get("optional_validations"))
    summary = {
        "pushed_ok": result["ok"], "http_status": result["status"],
        "push_error": result["push_error"], "run_id": result["run_id"],
        "found_by_lookup": result["found_by_lookup"], "run_error": result["run_error"],
        "still_running": bool(result["run_id"] and not row.get("end_time")),
        "needs_recheck": oc.needs_recheck(result),
        "started_ist": oc.ist(row.get("start_time")) if row else None,
        "errors": len(errors), "warnings": len(warnings),
        "error_groups": oc.group_issues(errors), "warning_groups": oc.group_issues(warnings),
        "response": result["text"][:600],
    }
    issues_csv = None
    if errors or warnings:
        out_dir.mkdir(parents=True, exist_ok=True)
        issues_csv = out_dir / f"onboarding_run_{result['run_id']}_issues.csv"
        rows = ([{"Severity": "Error", **e} for e in errors]
                + [{"Severity": "Warning", **w} for w in warnings])
        with open(issues_csv, "w", encoding="utf-8", newline="") as fh:   # plain UTF-8, no BOM
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        summary["issues_csv"] = str(issues_csv)
    print(json.dumps(summary, indent=2, default=str))

    if result["run_error"] or (result["run_id"] is None and oc.lost_answer(result)):
        return 3
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
