"""Guard against job-title drift between our tools and Uzio Company Master.

Run:  python utils/check_job_titles.py

Uzio's onboarding API resolves a job title by EXACT NAME
(`EmployeeCensusMapper.findJobTitleIdentifier` does a plain map lookup — no
trimming, no case folding). A title we offer that Company Master does not have
character-for-character is silently dropped during migration: no error, no log,
the employee just arrives with no job title.

That is not hypothetical. Every one of these was live at once (Aug 2026):
  * six files spelled it "Driver-Major Appliance"; Company Master code 028 is
    "Driver -Major Appliance", with a space before "Major"
  * audit_fast_api's catalog still had empty rows for J029/J030, so E-Biker and
    TSO-PV Driver did not exist for the MCP tools at all

Each of the three repos had a DIFFERENT subset correct, which is exactly the
mirror drift CLAUDE.md warns about — and none of it surfaced on its own,
because a wrong job title looks like no job title.

CANONICAL is transcribed from Company Master on prod. When Uzio adds a title
(e.g. PHIX-99297's Captain Planet Driver / Box Truck Driver), update it HERE
first, from the live screen — never from a ticket, which can differ in spacing —
then run this and fix whatever it reports.
"""
import csv
import os
import re
import sys

# Company Master -> Job Titles, codes 001-030, read off prod (Aug 2026).
CANONICAL = [
    "DSP Owner", "Operations Manager", "Operations Lead", "Fleet Manager",
    "Safety Manager", "Performance Manager", "Trainer", "Human Resources",
    "Recruiter", "Office Personnel", "Payroll Assistant", "Finance", "Dispatch",
    "Management", "Admin", "Survey", "Warehouse", "Walker", "Driver", "Helper",
    "Driver-Lite", "Driver-Step Van", "Driver-Unscheduled", "Lead Driver",
    "DDU Dedicated", "DDU Shared", "Non-DSP Related", "Driver -Major Appliance",
    "E-Biker", "TSO-PV Driver",
]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PY_LISTS = [
    "apps/adp/census_generator.py",
    "apps/paycom/census_generator.py",
    "implementors_repo/apps/adp/census_generator.py",
    "implementors_repo/apps/paycom/census_generator.py",
]
CSV_CATALOGS = [
    "templates/amazon_job_titles.csv",
    "implementors_repo/templates/amazon_job_titles.csv",
    "audit_fast_api/templates/amazon_job_titles.csv",
]


def allowed_from_py(path):
    src = open(path, encoding="utf-8").read()
    m = re.search(r"ALLOWED_JOB_TITLES\s*=\s*\[(.*?)\]", src, re.S)
    if not m:
        return None
    return re.findall(r"'([^']+)'", m.group(1))


def titles_from_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return [r["Job Title"].strip() for r in csv.DictReader(fh) if r.get("Job Title", "").strip()]


def main():
    canon = set(CANONICAL)
    problems = 0
    for rel in PY_LISTS + CSV_CATALOGS:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            print("SKIP      {} (not present)".format(rel))
            continue
        titles = allowed_from_py(path) if rel.endswith(".py") else titles_from_csv(path)
        if titles is None:
            print("MISMATCH  {} — ALLOWED_JOB_TITLES not found".format(rel))
            problems += 1
            continue
        extra = [t for t in titles if t not in canon]
        missing = [t for t in CANONICAL if t not in titles]
        if extra or missing:
            problems += 1
            print("MISMATCH  {}  ({} titles)".format(rel, len(titles)))
            for t in extra:
                print("             ours only : {!r}".format(t))
            for t in missing:
                print("             prod only : {!r}".format(t))
        else:
            print("OK        {}  ({} titles)".format(rel, len(titles)))
    print()
    if problems:
        print("{} list(s) differ from Company Master — fix them before shipping.".format(problems))
        return 1
    print("All lists match Company Master ({} titles).".format(len(CANONICAL)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
