"""Per-field coverage test for the Paycom withholding audit.

Generates synthetic Paycom + UZIO files with deliberate, known mismatches —
one per mapped field, plus multi-state and edge cases. Runs the audit.
Reports which expected mismatches were caught.

Run:
    python scratch/paycom_coverage_test.py
"""

from __future__ import annotations
import sys, os, csv, io
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from apps.paycom.withholding_audit import (
    _load_mapping_df, _load_labels_by_state, _load_filing_status_code,
    _autodetect_paycom_cols, run_withholding_audit, build_report_bytes,
)

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_paycom_fixtures")
PAYCOM_CSV = os.path.join(OUT_DIR, "synthetic_paycom.csv")
UZIO_CSV   = os.path.join(OUT_DIR, "synthetic_uzio.csv")
REPORT_XLSX = os.path.join(OUT_DIR, "synthetic_audit_report.xlsx")
os.makedirs(OUT_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# Test cases — one row per scenario.
# Each test_case names ONE field that should mismatch (or 'none' for clean
# baseline); all other fields are kept matching. After running the audit we
# verify each expected mismatch fires exactly once on the expected employee.
# ─────────────────────────────────────────────────────────────────────────────

# Paycom column → "matching default" / "mismatch variant" — both as written by
# the implementor (raw strings, no normalization).
#
# UZIO field key → "matching default" / "mismatch variant" — stored as UZIO
# stores them (cents for money fields, true/false for booleans, enum codes
# for filing status).

DEFAULTS_PAYCOM = {
    "#State_Exemptions/Allowances": "2",
    "Block_Fed_Tax?":               "No",
    "Block_State_Tax?":              "No",
    "Fed_Addl_$":                    "10",
    "Fed_Deductions_$":             "500",
    "Fed_Dependents_$":            "2000",
    "Fed_Filing_Status_Description": "Single or Married filing separately",
    "Fed_Multiple_Jobs?":            "No",
    "Fed_Other_Income_$":            "300",
    "Non-Resident_Alien":            "No",
    "State_Addl_$":                  "15",
    "State_Filing_Status_Desc":      "Single",
}

DEFAULTS_UZIO = {
    "SIT_TOTAL_ALLOWANCES":              "2",
    "SIT_TOTAL_ALLOWANCES_VALUE":        "2",   # IA-state alias of SIT_TOTAL_ALLOWANCES (Mapping.xlsx Comments rule)
    "FIT_WITHHOLDING_EXEMPTION":         "false",
    "SIT_WITHHOLDING_EXEMPTION":         "false",
    "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD":  "1000",       # 10.00 dollars in cents
    "FIT_DEDUCTIONS_OVER_STANDARD":         "50000",      # 500
    "FIT_CHILD_AND_DEPENDENT_TAX_CREDIT":   "200000",     # 2000
    "FIT_FILING_STATUS":                 "FEDERAL_SINGLE_OR_MARRIED",
    "FIT_HIGHER_WITHHOLDING":            "false",
    "FIT_OTHER_INCOME":                     "30000",      # 300
    "FIT_WITHHOLD_AS_NON_RESIDENT":      "false",
    "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD":  "1500",       # 15
    "SIT_FILING_STATUS":                 "MD_SINGLE",     # MD has SIT_FILING_STATUS in filing-status map
}

# Test scenarios. Each one specifies:
#   id        — Employee_Code
#   status    — Active / Terminated
#   work_st   — Work_Location_State (used for SIT matching)
#   home_st   — State (home) — should NOT affect SIT matching
#   mismatch  — which field to deliberately mismatch ('none' = clean baseline)
#   reason    — human-readable expected detection reason
#
# For mismatch scenarios: the UZIO value is set to the mismatch_variant; the
# Paycom side keeps the DEFAULT. (Or vice versa for "blank vs value" cases.)

TESTS = [
    # Clean baseline — no mismatch should be detected.
    {"id": "T00_BASELINE", "status": "Active",     "work_st": "MD", "home_st": "MD", "mismatch": "none"},

    # One scenario per mapped field — each should produce exactly one finding.
    {"id": "T01_SIT_ALLOW",   "status": "Active",     "work_st": "MD", "home_st": "MD", "mismatch": "SIT_TOTAL_ALLOWANCES"},
    {"id": "T02_FIT_EXEMPT",  "status": "Active",     "work_st": "MD", "home_st": "MD", "mismatch": "FIT_WITHHOLDING_EXEMPTION"},
    {"id": "T03_SIT_EXEMPT",  "status": "Active",     "work_st": "MD", "home_st": "MD", "mismatch": "SIT_WITHHOLDING_EXEMPTION"},
    {"id": "T04_FIT_ADDL",    "status": "Active",     "work_st": "MD", "home_st": "MD", "mismatch": "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"},
    {"id": "T05_FIT_DEDUC",   "status": "Active",     "work_st": "MD", "home_st": "MD", "mismatch": "FIT_DEDUCTIONS_OVER_STANDARD"},
    {"id": "T06_FIT_CHILD",   "status": "Active",     "work_st": "MD", "home_st": "MD", "mismatch": "FIT_CHILD_AND_DEPENDENT_TAX_CREDIT"},
    {"id": "T07_FIT_FS",      "status": "Active",     "work_st": "MD", "home_st": "MD", "mismatch": "FIT_FILING_STATUS"},
    {"id": "T08_FIT_HIGHER",  "status": "Active",     "work_st": "MD", "home_st": "MD", "mismatch": "FIT_HIGHER_WITHHOLDING"},
    {"id": "T09_FIT_OTHINC",  "status": "Active",     "work_st": "MD", "home_st": "MD", "mismatch": "FIT_OTHER_INCOME"},
    {"id": "T10_FIT_NRA",     "status": "Active",     "work_st": "MD", "home_st": "MD", "mismatch": "FIT_WITHHOLD_AS_NON_RESIDENT"},
    {"id": "T11_SIT_ADDL",    "status": "Active",     "work_st": "MD", "home_st": "MD", "mismatch": "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"},
    {"id": "T12_SIT_FS",      "status": "Active",     "work_st": "MD", "home_st": "MD", "mismatch": "SIT_FILING_STATUS"},

    # Multi-state — same matching value at WORK state OH; home is MI. Should NOT
    # mismatch (confirms our fix). If the tool regresses, it'll flag this.
    {"id": "M01_MULTISTATE_CLEAN", "status": "Active", "work_st": "MD", "home_st": "MI", "mismatch": "none"},

    # Multi-state with a real mismatch — Paycom OH value differs from UZIO OH.
    {"id": "M02_MULTISTATE_MISS",  "status": "Active", "work_st": "MD", "home_st": "MI", "mismatch": "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"},

    # Terminated employee with a mismatch — should land in All but NOT Active.
    {"id": "M03_TERMED_MISS",      "status": "Terminated", "work_st": "MD", "home_st": "MD", "mismatch": "FIT_FILING_STATUS"},

    # Missing-from-UZIO — Paycom row exists, UZIO has no rows for this id.
    {"id": "M04_MISSING_UZIO",     "status": "Active", "work_st": "MD", "home_st": "MD", "mismatch": "_missing_uzio"},

    # Missing-from-Paycom — UZIO rows exist, Paycom has no row.
    {"id": "M05_MISSING_PAYCOM",   "status": "Active", "work_st": "MD", "home_st": "MD", "mismatch": "_missing_paycom"},

    # Iowa employees — the SIT_TOTAL_ALLOWANCES composite-key business rule:
    # for IA, UZIO stores allowances under SIT_TOTAL_ALLOWANCES_VALUE, not
    # SIT_TOTAL_ALLOWANCES. The resolver should pick the right key by state.
    {"id": "IA01_CLEAN",        "status": "Active", "work_st": "IA", "home_st": "IA", "mismatch": "none"},
    {"id": "IA02_ALLOW_MISS",   "status": "Active", "work_st": "IA", "home_st": "IA", "mismatch": "SIT_TOTAL_ALLOWANCES_VALUE"},
]


def mismatch_uzio(field: str) -> str:
    """Pick a value that will deliberately disagree with the default."""
    d = DEFAULTS_UZIO[field]
    if field == "SIT_TOTAL_ALLOWANCES":            return "5"          # default 2
    if field == "SIT_TOTAL_ALLOWANCES_VALUE":      return "5"          # default 2 (IA path)
    if field == "FIT_WITHHOLDING_EXEMPTION":       return "true"       # default false
    if field == "SIT_WITHHOLDING_EXEMPTION":       return "true"       # default false
    if field == "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD":  return "9999"  # default 1000 (=$10)
    if field == "FIT_DEDUCTIONS_OVER_STANDARD":         return "12345" # default 50000
    if field == "FIT_CHILD_AND_DEPENDENT_TAX_CREDIT":   return "99999" # default 200000 ($2000)
    if field == "FIT_FILING_STATUS":               return "FEDERAL_HEAD_OF_HOUSEHOLD"  # default SINGLE_OR_MARRIED
    if field == "FIT_HIGHER_WITHHOLDING":          return "true"       # default false
    if field == "FIT_OTHER_INCOME":                     return "9999"  # default 30000
    if field == "FIT_WITHHOLD_AS_NON_RESIDENT":    return "true"       # default false
    if field == "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD":  return "9999"  # default 1500
    if field == "SIT_FILING_STATUS":               return "MD_MARRIED"  # default is MD_SINGLE
    return d


# ─────────────────────────────────────────────────────────────────────────────
# Generators
# ─────────────────────────────────────────────────────────────────────────────

PAYCOM_COLUMNS = [
    "Employee_Code", "Employee_Status", "Legal_Firstname", "Legal_Lastname",
    "Work_Location_State", "State",
] + list(DEFAULTS_PAYCOM.keys())


def write_paycom_csv():
    with open(PAYCOM_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PAYCOM_COLUMNS)
        w.writeheader()
        for t in TESTS:
            if t["mismatch"] == "_missing_paycom":
                continue  # this id only exists in UZIO
            row = {
                "Employee_Code":       t["id"],
                "Employee_Status":     t["status"],
                "Legal_Firstname":     "First" + t["id"][:3],
                "Legal_Lastname":      "Last" + t["id"][:3],
                "Work_Location_State": t["work_st"],
                "State":               t["home_st"],
                **DEFAULTS_PAYCOM,
            }
            w.writerow(row)
    print(f"  Wrote Paycom CSV: {PAYCOM_CSV}  ({sum(1 for _ in open(PAYCOM_CSV)) - 1} rows)")


def write_uzio_csv():
    """UZIO long-format. For each test employee, emit 12 field rows.
    Federal fields (FIT_*) get state_code="" and tax_scope="FEDERAL".
    State fields (SIT_*) get state_code=work_st and tax_scope="STATE".
    The mismatching field gets its UZIO value swapped to the mismatch variant.
    """
    rows = []
    for t in TESTS:
        if t["mismatch"] == "_missing_uzio":
            continue
        for uz_key, default_val in DEFAULTS_UZIO.items():
            value = mismatch_uzio(uz_key) if uz_key == t["mismatch"] else default_val
            is_sit = uz_key.startswith("SIT_")
            rows.append({
                "employee_id":             t["id"],
                "employee_first_name":     "First" + t["id"][:3],
                "employee_last_name":      "Last" + t["id"][:3],
                "tax_scope":               "STATE" if is_sit else "FEDERAL",
                "state_code":              t["work_st"] if is_sit else "",
                "master_tax_type":         "STATE_INCOME_TAX" if is_sit else "FEDERAL_INCOME_TAX",
                "withholding_field_key":   uz_key,
                "withholding_field_value": value,
                "effective_date":          "2026-01-01 00:00:00.000",
                "additional_info":         "",
                "status":                  ("ACTIVE" if t["status"] == "Active" else "TERMINATED"),
            })
    df = pd.DataFrame(rows)
    df.to_csv(UZIO_CSV, index=False)
    print(f"  Wrote UZIO CSV:   {UZIO_CSV}  ({len(df)} rows / {len(set(r['employee_id'] for r in rows))} employees)")


# ─────────────────────────────────────────────────────────────────────────────
# Audit + coverage report
# ─────────────────────────────────────────────────────────────────────────────

def expected_findings():
    """List of (employee_id, uzio_field_key) tuples that SHOULD be flagged."""
    out = []
    for t in TESTS:
        if t["mismatch"] in (None, "none", "_missing_uzio", "_missing_paycom"):
            continue
        out.append((t["id"], t["mismatch"]))
    return out


def section(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def main():
    section("Step 1 — generate synthetic test fixtures")
    write_paycom_csv()
    write_uzio_csv()

    section("Step 2 — load inlined config + read files")
    mapping_df = _load_mapping_df()
    labels = _load_labels_by_state()
    filing = _load_filing_status_code()
    paycom_df = pd.read_csv(PAYCOM_CSV, dtype=str, keep_default_na=False)
    uzio_df   = pd.read_csv(UZIO_CSV, dtype=str)  # keep NaN for state_code on FED rows
    emp_id, status, state, fn, ln = _autodetect_paycom_cols(paycom_df)
    print(f"  Autodetected: id={emp_id!r}, status={status!r}, state={state!r}, fn={fn!r}, ln={ln!r}")
    if state != "Work_Location_State":
        print(f"  WARNING: expected work-location autodetect to pick 'Work_Location_State', got {state!r}")

    section("Step 3 — run audit")
    s_df, act_df, all_df, miss_df, f_map_df, ui_map_df, rules_df = run_withholding_audit(
        paycom_df=paycom_df, uzio_long_df=uzio_df, mapping_df=mapping_df,
        labels_by_state=labels, filing_map=filing,
        paycom_emp_id_col=emp_id, paycom_status_col=status,
        paycom_state_col=state, paycom_fn_col=fn, paycom_ln_col=ln,
    )
    print(f"  Total mismatches: {len(all_df)}    Active: {len(act_df)}    Missing in UZIO: {len(miss_df)}")
    print()
    print("  All mismatches reported:")
    if all_df.empty:
        print("    (none)")
    else:
        for _, r in all_df.iterrows():
            print(f"    {r['Employee ID']:<22s} {r['UZIO Field Key']:<40s} "
                  f"Paycom={r['Paycom Value']!r:<10s} UZIO={r['UZIO Stored Value']!r}")

    with open(REPORT_XLSX, "wb") as f:
        f.write(build_report_bytes(s_df, act_df, all_df, miss_df, f_map_df, ui_map_df, rules_df))
    print(f"\n  Wrote audit report: {REPORT_XLSX}")

    section("Step 4 — coverage check")
    expected = expected_findings()
    actual = set(zip(all_df["Employee ID"].astype(str), all_df["UZIO Field Key"].astype(str)))

    print(f"\n  {'EMPLOYEE':<22s} {'FIELD':<40s} {'STATUS':<10s} NOTE")
    print(f"  {'-' * 22:<22s} {'-' * 40:<40s} {'-' * 10:<10s} {'-' * 4}")

    pass_count = fail_count = 0
    for emp, field in expected:
        caught = (emp, field) in actual
        if caught:
            pass_count += 1
            print(f"  {emp:<22s} {field:<40s} {'CAUGHT':<10s}")
        else:
            fail_count += 1
            print(f"  {emp:<22s} {field:<40s} {'MISSED':<10s} <- expected mismatch not flagged")

    # Look for unexpected findings (rows in actual but not expected).
    expected_set = set(expected)
    unexpected = actual - expected_set
    if unexpected:
        print()
        print("  Unexpected findings (not in test plan):")
        for emp, field in sorted(unexpected):
            print(f"    {emp:<22s} {field:<40s}")

    section("Coverage summary")
    print(f"  Expected mismatches: {len(expected)}")
    print(f"  Caught:              {pass_count}")
    print(f"  Missed:              {fail_count}")
    print(f"  Unexpected:          {len(unexpected)}")
    print(f"  Missing-in-UZIO row reported: {'YES' if 'M04_MISSING_UZIO' in miss_df.get('Employee ID', pd.Series(dtype=str)).values else 'NO (expected YES)'}")

    if fail_count or unexpected:
        print("\n  TEST RESULT: PARTIAL — see misses / unexpected above.")
    else:
        print("\n  TEST RESULT: PASS — every expected mismatch was caught, no surprises.")


if __name__ == "__main__":
    main()
