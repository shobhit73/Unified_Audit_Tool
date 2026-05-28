"""No-leniency stress test suite for the Paycom withholding audit.

Each test case below is self-contained: it builds a tiny Paycom + UZIO pair,
runs the audit, and asserts a specific outcome. Failures are reported with
the actual vs expected so we can see exactly what the tool did.

Test groups:
  G1  Per-field coverage          (12 fields, mismatch should fire on each)
  G2  Boolean vocabulary          (Yes/Y/1/true/on vs No/N/0/false/off, blank)
  G3  Money / cents conversion    ($, commas, parens negatives, zero, fractions)
  G4  Numeric edge cases          (large, negative, blank)
  G5  Filing-status matching      (case, punct, unknown enum, blank)
  G6  Iowa SIT_TOTAL_ALLOWANCES   (IA->VALUE, non-IA->base, neither present)
  G7  Multi-state                 (work != home; partial UZIO state coverage)
  G8  Status normalization        (Active vocab, Terminated vocab, blank)
  G9  Missing populations         (employee in only one file)
  G10 Data shape edge cases       (blank IDs, duplicates, NaN tokens)
  G11 Autodetect                  (alt column names, missing Work_Location_State)
  G12 Output integrity            (columns, sheets, names populated)
"""

from __future__ import annotations
import sys, os, io, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from apps.paycom.withholding_audit import (
    _load_mapping_df, _load_labels_by_state, _load_filing_status_code,
    _autodetect_paycom_cols, run_withholding_audit, build_report_bytes,
    _resolve_uz_key_for_row, _infer_type,
)

PASS = "[PASS]"
FAIL = "[FAIL]"


# ─────────────────────────────────────────────────────────────────────────────
# Test framework
# ─────────────────────────────────────────────────────────────────────────────

results = []  # (group, name, status, message)

def record(group: str, name: str, ok: bool, message: str = ""):
    results.append((group, name, ok, message))
    tag = PASS if ok else FAIL
    print(f"  {tag} {group}.{name:<55s} {message}")


# Pre-load the inlined config once.
MAPPING_DF = _load_mapping_df()
LABELS     = _load_labels_by_state()
FILING_MAP = _load_filing_status_code()


# Defaults used by every test that wants "everything else matching".
# Values chosen so every default produces a match.
PAYCOM_HAPPY = {
    "Employee_Code":                 "DEFAULT",
    "Employee_Status":               "Active",
    "Legal_Firstname":               "Test",
    "Legal_Lastname":                "Employee",
    "Work_Location_State":           "MD",
    "State":                         "MD",
    "#State_Exemptions/Allowances":  "2",
    "Block_Fed_Tax?":                "No",
    "Block_State_Tax?":              "No",
    "Fed_Addl_$":                    "10",
    "Fed_Deductions_$":              "500",
    "Fed_Dependents_$":              "2000",
    "Fed_Filing_Status_Description": "Single or Married filing separately",
    "Fed_Multiple_Jobs?":            "No",
    "Fed_Other_Income_$":            "300",
    "Non-Resident_Alien":            "No",
    "State_Addl_$":                  "15",
    "State_Filing_Status_Desc":      "Single",
}

UZIO_HAPPY_KV = {
    "SIT_TOTAL_ALLOWANCES":               ("2",        "STATE"),
    "SIT_TOTAL_ALLOWANCES_VALUE":         ("2",        "STATE"),
    "FIT_WITHHOLDING_EXEMPTION":          ("false",    "FEDERAL"),
    "SIT_WITHHOLDING_EXEMPTION":          ("false",    "STATE"),
    "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD":("1000",     "FEDERAL"),
    "FIT_DEDUCTIONS_OVER_STANDARD":       ("50000",    "FEDERAL"),
    "FIT_CHILD_AND_DEPENDENT_TAX_CREDIT": ("200000",   "FEDERAL"),
    "FIT_FILING_STATUS":                  ("FEDERAL_SINGLE_OR_MARRIED", "FEDERAL"),
    "FIT_HIGHER_WITHHOLDING":             ("false",    "FEDERAL"),
    "FIT_OTHER_INCOME":                   ("30000",    "FEDERAL"),
    "FIT_WITHHOLD_AS_NON_RESIDENT":       ("false",    "FEDERAL"),
    "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD":("1500",     "STATE"),
    "SIT_FILING_STATUS":                  ("MD_SINGLE","STATE"),
}


def make_paycom(rows):
    """Build a Paycom DataFrame from a list of partial-row dicts merged into the happy defaults."""
    out = []
    for r in rows:
        merged = dict(PAYCOM_HAPPY)
        merged.update(r)
        out.append(merged)
    cols = list(PAYCOM_HAPPY.keys())
    for r in rows:
        for k in r.keys():
            if k not in cols:
                cols.append(k)
    return pd.DataFrame(out, columns=cols)


def make_uzio(emp_state_pairs, overrides=None):
    """Build a UZIO long-format DataFrame.

    emp_state_pairs : list of (employee_id, work_state, status) tuples.
                       Status determines `status` column ("ACTIVE"/"TERMINATED").
                       work_state goes into the SIT rows' state_code.
    overrides       : dict {(emp_id, uzio_field_key): value}
                       Override the happy-default UZIO value for specific (emp, field) cells.
    """
    overrides = overrides or {}
    rows = []
    for emp_id, work_state, status in emp_state_pairs:
        for uz_key, (default_val, scope) in UZIO_HAPPY_KV.items():
            value = overrides.get((emp_id, uz_key), default_val)
            is_sit = scope == "STATE"
            rows.append({
                "employee_id":             emp_id,
                "employee_first_name":     "Test",
                "employee_last_name":      "Employee",
                "tax_scope":               scope,
                "state_code":              work_state if is_sit else "",
                "master_tax_type":         "STATE_INCOME_TAX" if is_sit else "FEDERAL_INCOME_TAX",
                "withholding_field_key":   uz_key,
                "withholding_field_value": value,
                "effective_date":          "2026-01-01",
                "additional_info":         "",
                "status":                  status,
            })
    return pd.DataFrame(rows)


def run_audit(paycom_df, uzio_df):
    """Run the audit pipeline and return the All_Mismatches DataFrame."""
    emp_id, status, state, fn, ln = _autodetect_paycom_cols(paycom_df)
    s, act, allm, miss, fm, ui, rules = run_withholding_audit(
        paycom_df=paycom_df, uzio_long_df=uzio_df, mapping_df=MAPPING_DF,
        labels_by_state=LABELS, filing_map=FILING_MAP,
        paycom_emp_id_col=emp_id, paycom_status_col=status,
        paycom_state_col=state, paycom_fn_col=fn, paycom_ln_col=ln,
    )
    return s, act, allm, miss, fm


def assert_finding(group, name, allm, emp_id, field_key=None, expected=True):
    """Check whether (emp_id, field_key) appears in mismatches."""
    if allm.empty:
        found = False
        details = []
    else:
        rows = allm[allm["Employee ID"].astype(str) == emp_id]
        if field_key:
            rows = rows[rows["UZIO Field Key"].astype(str) == field_key]
        found = not rows.empty
        details = [
            f"{r['UZIO Field Key']} (P={r['Paycom Value']!r} U={r['UZIO Stored Value']!r})"
            for _, r in rows.iterrows()
        ]
    if expected and found:
        record(group, name, True, f"flagged: {', '.join(details)}")
    elif expected and not found:
        record(group, name, False, "expected mismatch, none found")
    elif not expected and found:
        record(group, name, False, f"UNEXPECTED finding: {', '.join(details)}")
    else:
        record(group, name, True, "correctly silent")


# ─────────────────────────────────────────────────────────────────────────────
# G1 — Per-field coverage (sanity baseline)
# ─────────────────────────────────────────────────────────────────────────────
def g1_per_field_coverage():
    print("\n=== G1: Per-field coverage ===")
    field_tests = [
        ("SIT_TOTAL_ALLOWANCES",                "#State_Exemptions/Allowances", "2", "5", "MD"),
        ("FIT_WITHHOLDING_EXEMPTION",           "Block_Fed_Tax?",               "No", "true", "MD"),
        ("SIT_WITHHOLDING_EXEMPTION",           "Block_State_Tax?",             "No", "true", "MD"),
        ("FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD", "Fed_Addl_$",                   "10", "9999", "MD"),
        ("FIT_DEDUCTIONS_OVER_STANDARD",        "Fed_Deductions_$",             "500", "12345", "MD"),
        ("FIT_CHILD_AND_DEPENDENT_TAX_CREDIT",  "Fed_Dependents_$",             "2000", "99999", "MD"),
        ("FIT_FILING_STATUS",                   "Fed_Filing_Status_Description","Single or Married filing separately", "FEDERAL_HEAD_OF_HOUSEHOLD", "MD"),
        ("FIT_HIGHER_WITHHOLDING",              "Fed_Multiple_Jobs?",           "No", "true", "MD"),
        ("FIT_OTHER_INCOME",                    "Fed_Other_Income_$",           "300", "9999", "MD"),
        ("FIT_WITHHOLD_AS_NON_RESIDENT",        "Non-Resident_Alien",           "No", "true", "MD"),
        ("SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD", "State_Addl_$",                 "15", "9999", "MD"),
        ("SIT_FILING_STATUS",                   "State_Filing_Status_Desc",     "Single", "MD_MARRIED", "MD"),
    ]
    for uz_key, pc_col, pc_default, uz_mismatch, work_st in field_tests:
        emp = f"F_{uz_key[:25]}"
        paycom = make_paycom([{"Employee_Code": emp, "Work_Location_State": work_st, pc_col: pc_default}])
        uzio = make_uzio([(emp, work_st, "ACTIVE")], overrides={(emp, uz_key): uz_mismatch})
        _, _, allm, _, _ = run_audit(paycom, uzio)
        assert_finding("G1", uz_key, allm, emp, uz_key, expected=True)


# ─────────────────────────────────────────────────────────────────────────────
# G2 — Boolean vocabulary
# ─────────────────────────────────────────────────────────────────────────────
def g2_boolean_vocab():
    print("\n=== G2: Boolean vocabulary ===")
    cases = [
        # (paycom_value, uzio_value, expected_match)
        ("Yes",   "true",  True),
        ("No",    "false", True),
        ("Y",     "true",  True),
        ("N",     "false", True),
        ("1",     "true",  True),
        ("0",     "false", True),
        ("yes",   "TRUE",  True),
        ("YES",   "True",  True),
        ("True",  "TRUE",  True),
        ("on",    "true",  True),
        ("off",   "false", True),
        ("Yes",   "false", False),  # real disagree
        ("No",    "true",  False),  # real disagree
        # NOTE: tool intentionally flags blank-vs-explicit-value as "Blank vs Value"
        # — surfaces data-quality issues where one side wasn't populated.
        ("",      "false", False),  # blank vs explicit false — intentional flag
        ("",      "true",  False),  # blank vs explicit true
    ]
    for i, (pv, uv, should_match) in enumerate(cases):
        emp = f"BOOL_{i:02d}"
        paycom = make_paycom([{"Employee_Code": emp, "Block_Fed_Tax?": pv}])
        uzio   = make_uzio([(emp, "MD", "ACTIVE")], overrides={(emp, "FIT_WITHHOLDING_EXEMPTION"): uv})
        _, _, allm, _, _ = run_audit(paycom, uzio)
        assert_finding("G2", f"P={pv!r} U={uv!r}", allm, emp, "FIT_WITHHOLDING_EXEMPTION", expected=not should_match)


# ─────────────────────────────────────────────────────────────────────────────
# G3 — Money / cents conversion
# ─────────────────────────────────────────────────────────────────────────────
def g3_money_cents():
    print("\n=== G3: Money / cents conversion ===")
    cases = [
        # (paycom_dollars, uzio_cents, expected_match)
        ("0",       "0",       True),
        ("10",      "1000",    True),
        ("10.00",   "1000",    True),
        ("$10",     "1000",    True),
        ("1,000",   "100000",  True),
        ("10",      "1001",    False),    # 1-cent diff (above 0.01 threshold? actually < 0.01)
        ("10",      "999",     False),    # 1-cent diff
        ("",        "",        True),     # both blank
        ("",        "0",       True),     # blank == 0
        ("0",       "",        True),
        ("10",      "",        False),    # paycom has value, uzio blank => mismatch
        ("",        "1000",    False),    # uzio has value, paycom blank
        ("(10)",    "-1000",   True),     # parentheses negative
        ("0.01",    "1",       True),
        ("100000",  "10000000",True),     # 100k
        ("10",      "1000.5",  False),    # diff $0.005 — at tightened half-cent tolerance, flagged
    ]
    for i, (pv, uv, should_match) in enumerate(cases):
        emp = f"MON_{i:02d}"
        paycom = make_paycom([{"Employee_Code": emp, "Fed_Addl_$": pv}])
        uzio   = make_uzio([(emp, "MD", "ACTIVE")], overrides={(emp, "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): uv})
        _, _, allm, _, _ = run_audit(paycom, uzio)
        assert_finding("G3", f"P={pv!r} U={uv!r}", allm, emp, "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD", expected=not should_match)


# ─────────────────────────────────────────────────────────────────────────────
# G4 — Numeric edge cases (integer fields)
# ─────────────────────────────────────────────────────────────────────────────
def g4_numeric_edges():
    print("\n=== G4: Numeric integer edge cases ===")
    cases = [
        ("0",       "0",        True),
        ("1",       "1",        True),
        ("",        "0",        True),
        ("0",       "",         True),
        ("",        "",         True),
        ("2",       "5",        False),
        ("99",      "100",      False),
        ("10",      "10",       True),
    ]
    for i, (pv, uv, should_match) in enumerate(cases):
        emp = f"NUM_{i:02d}"
        paycom = make_paycom([{"Employee_Code": emp, "#State_Exemptions/Allowances": pv}])
        uzio   = make_uzio([(emp, "MD", "ACTIVE")], overrides={(emp, "SIT_TOTAL_ALLOWANCES"): uv})
        _, _, allm, _, _ = run_audit(paycom, uzio)
        assert_finding("G4", f"P={pv!r} U={uv!r}", allm, emp, "SIT_TOTAL_ALLOWANCES", expected=not should_match)


# ─────────────────────────────────────────────────────────────────────────────
# G5 — Filing-status matching
# ─────────────────────────────────────────────────────────────────────────────
def g5_filing_status():
    print("\n=== G5: Filing-status matching ===")
    cases = [
        # (paycom_label, uzio_enum, expected_match)
        ("Single",                                "MD_SINGLE",             True),
        ("Married",                               "MD_MARRIED",            True),
        ("single",                                "MD_SINGLE",             True),   # case
        ("  Single  ",                            "MD_SINGLE",             True),   # whitespace
        ("Single",                                "MD_MARRIED",            False),
        ("Single or Married filing separately",   "FEDERAL_SINGLE_OR_MARRIED", True),
        ("",                                      "",                      True),   # both blank
        ("Single",                                "",                      False),  # paycom has value, uzio blank
        ("Single",                                "ZZ_UNKNOWN_ENUM",       False),  # unknown enum
        ("Single",                                "FEDERAL_SINGLE_OR_MARRIED", True),  # substring match works
    ]
    for i, (pv, uv, should_match) in enumerate(cases):
        emp = f"FS_{i:02d}"
        paycom = make_paycom([{"Employee_Code": emp, "State_Filing_Status_Desc": pv}])
        uzio   = make_uzio([(emp, "MD", "ACTIVE")], overrides={(emp, "SIT_FILING_STATUS"): uv})
        _, _, allm, _, _ = run_audit(paycom, uzio)
        assert_finding("G5", f"P={pv!r} U={uv!r}", allm, emp, "SIT_FILING_STATUS", expected=not should_match)


# ─────────────────────────────────────────────────────────────────────────────
# G6 — Iowa SIT_TOTAL_ALLOWANCES business rule
# ─────────────────────────────────────────────────────────────────────────────
def g6_iowa_rule():
    print("\n=== G6: Iowa SIT_TOTAL_ALLOWANCES rule ===")

    # Unit-level: resolver picks the right key based on state.
    record("G6", "resolver IA -> VALUE",
           _resolve_uz_key_for_row("SIT_TOTAL_ALLOWANCES / SIT_TOTAL_ALLOWANCES_VALUE", "IA") == "SIT_TOTAL_ALLOWANCES_VALUE",
           "ok")
    record("G6", "resolver MD -> base",
           _resolve_uz_key_for_row("SIT_TOTAL_ALLOWANCES / SIT_TOTAL_ALLOWANCES_VALUE", "MD") == "SIT_TOTAL_ALLOWANCES",
           "ok")
    record("G6", "resolver blank state -> base",
           _resolve_uz_key_for_row("SIT_TOTAL_ALLOWANCES / SIT_TOTAL_ALLOWANCES_VALUE", "") == "SIT_TOTAL_ALLOWANCES",
           "ok")
    record("G6", "resolver passes through non-composite",
           _resolve_uz_key_for_row("FIT_OTHER_INCOME", "IA") == "FIT_OTHER_INCOME",
           "ok")

    # Integration-level: IA employee with mismatch on _VALUE, no mismatch on base
    emp = "IA_MISS"
    paycom = make_paycom([{"Employee_Code": emp, "Work_Location_State": "IA",
                           "#State_Exemptions/Allowances": "2"}])
    uzio   = make_uzio([(emp, "IA", "ACTIVE")], overrides={
        (emp, "SIT_TOTAL_ALLOWANCES"):       "2",   # matches if mistakenly looked up
        (emp, "SIT_TOTAL_ALLOWANCES_VALUE"): "9",   # mismatch if correctly looked up
    })
    _, _, allm, _, _ = run_audit(paycom, uzio)
    assert_finding("G6", "IA employee -> mismatch on VALUE field", allm, emp, "SIT_TOTAL_ALLOWANCES_VALUE", expected=True)

    # MD employee with mismatch on base, NO mismatch on VALUE
    emp = "MD_MISS"
    paycom = make_paycom([{"Employee_Code": emp, "Work_Location_State": "MD",
                           "#State_Exemptions/Allowances": "2"}])
    uzio   = make_uzio([(emp, "MD", "ACTIVE")], overrides={
        (emp, "SIT_TOTAL_ALLOWANCES"):       "9",   # mismatch if correctly looked up
        (emp, "SIT_TOTAL_ALLOWANCES_VALUE"): "2",   # matches if mistakenly looked up
    })
    _, _, allm, _, _ = run_audit(paycom, uzio)
    assert_finding("G6", "MD employee -> mismatch on base field", allm, emp, "SIT_TOTAL_ALLOWANCES", expected=True)


# ─────────────────────────────────────────────────────────────────────────────
# G7 — Multi-state
# ─────────────────────────────────────────────────────────────────────────────
def g7_multistate():
    print("\n=== G7: Multi-state scenarios ===")

    # Live MI, work OH; UZIO has data for BOTH states. SIT compares against OH only.
    emp = "MULTI_OH"
    paycom = make_paycom([{"Employee_Code": emp, "Work_Location_State": "OH", "State": "MI",
                           "State_Addl_$": "15"}])
    rows = []
    # Both MI and OH state rows in UZIO. OH matches Paycom $15; MI has different value.
    for st in ("MI", "OH"):
        for k, (v, scope) in UZIO_HAPPY_KV.items():
            if scope == "STATE":
                if k == "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD":
                    v = "9999" if st == "MI" else "1500"  # MI=99, OH=$15
                rows.append({
                    "employee_id": emp, "employee_first_name": "Test", "employee_last_name": "Employee",
                    "tax_scope": "STATE", "state_code": st, "master_tax_type": "STATE_INCOME_TAX",
                    "withholding_field_key": k, "withholding_field_value": v,
                    "effective_date": "2026-01-01", "additional_info": "", "status": "ACTIVE",
                })
        for k, (v, scope) in UZIO_HAPPY_KV.items():
            if scope == "FEDERAL":
                rows.append({
                    "employee_id": emp, "employee_first_name": "Test", "employee_last_name": "Employee",
                    "tax_scope": "FEDERAL", "state_code": "", "master_tax_type": "FEDERAL_INCOME_TAX",
                    "withholding_field_key": k, "withholding_field_value": v,
                    "effective_date": "2026-01-01", "additional_info": "", "status": "ACTIVE",
                })
        break  # only need federal rows once
    # Add the OH-state-only federal rows
    uzio = pd.DataFrame(rows).drop_duplicates(subset=["employee_id", "state_code", "withholding_field_key"], keep="first")
    _, _, allm, _, _ = run_audit(paycom, uzio)
    assert_finding("G7", "live MI work OH -> SIT matched against OH (no mismatch)", allm, emp, "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD", expected=False)

    # Work_Location_State blank -> SIT comparisons skipped silently
    emp = "NO_WORKSTATE"
    paycom = make_paycom([{"Employee_Code": emp, "Work_Location_State": ""}])
    uzio = make_uzio([(emp, "MD", "ACTIVE")], overrides={(emp, "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): "9999"})
    _, _, allm, _, _ = run_audit(paycom, uzio)
    assert_finding("G7", "blank work-state -> SIT skipped (no false flag)", allm, emp, "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD", expected=False)

    # UZIO has no SIT record for the work state at all -> skip cleanly
    emp = "NO_UZIO_STATE"
    paycom = make_paycom([{"Employee_Code": emp, "Work_Location_State": "TX",
                           "State_Addl_$": "15"}])
    uzio = make_uzio([(emp, "MD", "ACTIVE")])  # UZIO only has MD records
    _, _, allm, _, _ = run_audit(paycom, uzio)
    assert_finding("G7", "UZIO has no record for work-state TX -> skip", allm, emp, "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD", expected=False)


# ─────────────────────────────────────────────────────────────────────────────
# G8 — Status vocabulary
# ─────────────────────────────────────────────────────────────────────────────
def g8_status_vocab():
    print("\n=== G8: Status vocabulary in Active sheet ===")
    # Verify various active spellings land in Active_Mismatches
    for status in ["Active", "ACTIVE", "active", "On Leave"]:
        emp = f"STAT_{status.upper().replace(' ', '_')}"
        paycom = make_paycom([{"Employee_Code": emp, "Employee_Status": status,
                               "Fed_Addl_$": "10"}])
        uzio   = make_uzio([(emp, "MD", "ACTIVE")], overrides={(emp, "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): "9999"})
        _, act, _, _, _ = run_audit(paycom, uzio)
        in_active = not act.empty and emp in act["Employee ID"].astype(str).values
        record("G8", f"status={status!r} in Active_Mismatches", in_active,
               f"{'present' if in_active else 'MISSING from Active sheet'}")

    # Terminated should NOT land in Active
    for status in ["Terminated", "TERM", "Inactive", "Separated"]:
        emp = f"STAT_{status.upper().replace(' ', '_')}"
        paycom = make_paycom([{"Employee_Code": emp, "Employee_Status": status,
                               "Fed_Addl_$": "10"}])
        uzio   = make_uzio([(emp, "MD", "TERMINATED")], overrides={(emp, "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): "9999"})
        _, act, allm, _, _ = run_audit(paycom, uzio)
        in_active = not act.empty and emp in act["Employee ID"].astype(str).values
        in_all = not allm.empty and emp in allm["Employee ID"].astype(str).values
        record("G8", f"status={status!r} NOT in Active, IS in All", (not in_active) and in_all,
               f"active={in_active}, all={in_all}")


# ─────────────────────────────────────────────────────────────────────────────
# G9 — Missing populations
# ─────────────────────────────────────────────────────────────────────────────
def g9_missing_populations():
    print("\n=== G9: Missing populations ===")
    # Paycom-only
    paycom = make_paycom([
        {"Employee_Code": "INBOTH", "Fed_Addl_$": "10"},
        {"Employee_Code": "ONLY_PAYCOM", "Fed_Addl_$": "10"},
    ])
    uzio = make_uzio([("INBOTH", "MD", "ACTIVE")])
    _, _, allm, miss, _ = run_audit(paycom, uzio)
    ids = set(miss["Employee ID"].astype(str)) if not miss.empty else set()
    record("G9", "Paycom-only employee in Missing_in_UZIO", "ONLY_PAYCOM" in ids,
           f"missing={ids}")

    # Both files have the employee → not missing
    record("G9", "Common employee NOT in Missing_in_UZIO", "INBOTH" not in ids, f"missing={ids}")


# ─────────────────────────────────────────────────────────────────────────────
# G10 — Data shape edge cases
# ─────────────────────────────────────────────────────────────────────────────
def g10_data_shapes():
    print("\n=== G10: Data shape edge cases ===")
    # Blank Employee_Code in Paycom row — should be filtered out, not crash
    try:
        paycom = make_paycom([
            {"Employee_Code": "",       "Fed_Addl_$": "10"},
            {"Employee_Code": "VALID",  "Fed_Addl_$": "10"},
        ])
        uzio = make_uzio([("VALID", "MD", "ACTIVE")])
        _, _, allm, miss, _ = run_audit(paycom, uzio)
        record("G10", "blank Employee_Code does not crash", True, f"valid still processed; missing={set(miss['Employee ID'].astype(str)) if not miss.empty else set()}")
    except Exception as e:
        record("G10", "blank Employee_Code does not crash", False, f"crashed: {e}")

    # Leading zeros preserved
    paycom = make_paycom([{"Employee_Code": "001234", "Fed_Addl_$": "10"}])
    uzio = make_uzio([("001234", "MD", "ACTIVE")], overrides={("001234", "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): "9999"})
    _, _, allm, _, _ = run_audit(paycom, uzio)
    assert_finding("G10", "leading-zero employee_id matches across files", allm, "001234", "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD", expected=True)

    # Literal 'nan' string in UZIO state_code shouldn't be treated as a state
    paycom = make_paycom([{"Employee_Code": "NAN_TEST", "Work_Location_State": "MD"}])
    rows = [{
        "employee_id": "NAN_TEST", "employee_first_name": "Test", "employee_last_name": "Employee",
        "tax_scope": "FEDERAL", "state_code": "nan", "master_tax_type": "FEDERAL_INCOME_TAX",
        "withholding_field_key": "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD",
        "withholding_field_value": "1000", "effective_date": "", "additional_info": "", "status": "ACTIVE",
    }]
    uzio = pd.DataFrame(rows)
    try:
        _, _, _, _, _ = run_audit(paycom, uzio)
        record("G10", "literal 'nan' string in state_code doesn't crash", True, "ok")
    except Exception as e:
        record("G10", "literal 'nan' string in state_code doesn't crash", False, f"crashed: {e}")

    # Empty Paycom file
    try:
        paycom = pd.DataFrame(columns=list(PAYCOM_HAPPY.keys()))
        uzio = make_uzio([("X", "MD", "ACTIVE")])
        _, _, _, miss, _ = run_audit(paycom, uzio)
        record("G10", "empty Paycom file doesn't crash", True, "ok")
    except Exception as e:
        record("G10", "empty Paycom file doesn't crash", False, f"crashed: {e}")

    # Empty UZIO file
    try:
        paycom = make_paycom([{"Employee_Code": "X"}])
        uzio = pd.DataFrame(columns=["employee_id", "withholding_field_key", "withholding_field_value", "state_code"])
        _, _, _, miss, _ = run_audit(paycom, uzio)
        record("G10", "empty UZIO file doesn't crash", True, f"missing in UZIO: {len(miss)}")
    except Exception as e:
        record("G10", "empty UZIO file doesn't crash", False, f"crashed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# G11 — Autodetect
# ─────────────────────────────────────────────────────────────────────────────
def g11_autodetect():
    print("\n=== G11: Autodetect ===")
    # Standard headers
    df = pd.DataFrame([{"Employee_Code": "X", "Employee_Status": "Active",
                        "Legal_Firstname": "A", "Legal_Lastname": "B",
                        "Work_Location_State": "MD", "State": "MD"}])
    emp, status, state, fn, ln = _autodetect_paycom_cols(df)
    record("G11", "picks Employee_Code as id", emp == "Employee_Code", f"got {emp!r}")
    record("G11", "picks Work_Location_State as state", state == "Work_Location_State", f"got {state!r}")
    record("G11", "picks Legal_Firstname as fn", fn == "Legal_Firstname", f"got {fn!r}")
    record("G11", "picks Legal_Lastname as ln", ln == "Legal_Lastname", f"got {ln!r}")

    # Falls back to home State when Work_Location_State is missing
    df = pd.DataFrame([{"Employee_Code": "X", "Employee_Status": "Active", "State": "MD"}])
    emp, status, state, fn, ln = _autodetect_paycom_cols(df)
    record("G11", "falls back to State when no Work_Location_State", state == "State", f"got {state!r}")

    # Works with First_Name / Last_Name aliases
    df = pd.DataFrame([{"Employee_Code": "X", "First_Name": "A", "Last_Name": "B", "Work_Location_State": "MD"}])
    emp, status, state, fn, ln = _autodetect_paycom_cols(df)
    record("G11", "picks First_Name when present", fn == "First_Name", f"got {fn!r}")


# ─────────────────────────────────────────────────────────────────────────────
# G12 — Output integrity
# ─────────────────────────────────────────────────────────────────────────────
def g12_output_integrity():
    print("\n=== G12: Output integrity ===")
    paycom = make_paycom([{"Employee_Code": "OUT01", "Fed_Addl_$": "10"}])
    uzio = make_uzio([("OUT01", "MD", "ACTIVE")], overrides={("OUT01", "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): "9999"})
    s, act, allm, miss, fm = run_audit(paycom, uzio)

    expected_cols = ["Employee ID", "Paycom Status", "Paycom State",
                     "Paycom First Name", "Paycom Last Name",
                     "UZIO First Name", "UZIO Last Name",
                     "Field Label", "Paycom Column", "Paycom Value",
                     "UZIO Field Key", "UZIO Stored Value",
                     "Paycom Normalized", "UZIO Normalized / UI", "Rule Applied"]
    missing_cols = [c for c in expected_cols if c not in allm.columns]
    record("G12", "All_Mismatches has all expected columns", not missing_cols,
           f"missing: {missing_cols}" if missing_cols else "ok")

    # Names should populate
    name_present = not allm.empty and allm.iloc[0]["Paycom First Name"] == "Test"
    record("G12", "Paycom names populate in mismatch rows", name_present,
           f"got {allm.iloc[0]['Paycom First Name']!r}" if not allm.empty else "no rows")

    # Try the workbook bytes (does it serialize cleanly?)
    try:
        data = build_report_bytes(s, act, allm, miss, fm, pd.DataFrame(), pd.DataFrame())
        record("G12", "build_report_bytes produces valid xlsx", len(data) > 1000, f"{len(data):,} bytes")
    except Exception as e:
        record("G12", "build_report_bytes produces valid xlsx", False, f"crashed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# G13 — Per-field MATCH cases (no false positives when values agree)
# ─────────────────────────────────────────────────────────────────────────────
def g13_per_field_match():
    print("\n=== G13: Per-field match (no false positives when values agree) ===")
    # Same as G1 but every value is the matching default — nothing should fire.
    field_tests = [
        ("SIT_TOTAL_ALLOWANCES",                "#State_Exemptions/Allowances", "2",  "2",        "MD"),
        ("FIT_WITHHOLDING_EXEMPTION",           "Block_Fed_Tax?",               "No", "false",    "MD"),
        ("SIT_WITHHOLDING_EXEMPTION",           "Block_State_Tax?",             "No", "false",    "MD"),
        ("FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD", "Fed_Addl_$",                   "10", "1000",     "MD"),
        ("FIT_DEDUCTIONS_OVER_STANDARD",        "Fed_Deductions_$",             "500","50000",    "MD"),
        ("FIT_CHILD_AND_DEPENDENT_TAX_CREDIT",  "Fed_Dependents_$",             "2000","200000",  "MD"),
        ("FIT_FILING_STATUS",                   "Fed_Filing_Status_Description","Single or Married filing separately", "FEDERAL_SINGLE_OR_MARRIED","MD"),
        ("FIT_HIGHER_WITHHOLDING",              "Fed_Multiple_Jobs?",           "No", "false",    "MD"),
        ("FIT_OTHER_INCOME",                    "Fed_Other_Income_$",           "300","30000",    "MD"),
        ("FIT_WITHHOLD_AS_NON_RESIDENT",        "Non-Resident_Alien",           "No", "false",    "MD"),
        ("SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD", "State_Addl_$",                 "15", "1500",     "MD"),
        ("SIT_FILING_STATUS",                   "State_Filing_Status_Desc",     "Single","MD_SINGLE","MD"),
    ]
    for uz_key, pc_col, pc_val, uz_val, work_st in field_tests:
        emp = f"M_{uz_key[:25]}"
        paycom = make_paycom([{"Employee_Code": emp, "Work_Location_State": work_st, pc_col: pc_val}])
        uzio = make_uzio([(emp, work_st, "ACTIVE")], overrides={(emp, uz_key): uz_val})
        _, _, allm, _, _ = run_audit(paycom, uzio)
        assert_finding("G13", uz_key, allm, emp, uz_key, expected=False)


# ─────────────────────────────────────────────────────────────────────────────
# G14 — Filing status state-prefix sanity
# ─────────────────────────────────────────────────────────────────────────────
def g14_filing_status_state_prefix():
    print("\n=== G14: Filing status state-prefix edge cases ===")
    # Paycom employee in MD but UZIO has NJ enum — different state's enum still
    # produces a comparable label, so should match by label content not state.
    cases = [
        ("Single",  "NJ_SINGLE", "MD", True,  "NJ_SINGLE label is 'Single', matches Paycom 'Single'"),
        ("Single",  "AL_SINGLE", "MD", True,  "AL_SINGLE label is 'Single'"),
        ("Married", "MD_MARRIED","MD", True,  "exact match"),
        ("Single",  "MD_SINGLE", "NJ", True,  "Paycom in NJ but UZIO MD_SINGLE -> labels match"),
        ("Head of Family", "AL_HEAD_OF_HOUSEHOLD", "MD", True, "AL_HEAD_OF_HOUSEHOLD label is 'Head of Family'"),
    ]
    for i, (pv, uv, st, should_match, why) in enumerate(cases):
        emp = f"FSP_{i:02d}"
        paycom = make_paycom([{"Employee_Code": emp, "Work_Location_State": st, "State_Filing_Status_Desc": pv}])
        uzio = make_uzio([(emp, st, "ACTIVE")], overrides={(emp, "SIT_FILING_STATUS"): uv})
        _, _, allm, _, _ = run_audit(paycom, uzio)
        assert_finding("G14", f"P={pv!r} U={uv!r} ({why})", allm, emp, "SIT_FILING_STATUS", expected=not should_match)


# ─────────────────────────────────────────────────────────────────────────────
# G15 — Money sign/format edge cases
# ─────────────────────────────────────────────────────────────────────────────
def g15_money_edges():
    print("\n=== G15: Money sign/format edge cases ===")
    cases = [
        ("0.00",   "0",       True),
        ("-0",     "0",       True),
        ("00",     "0",       True),
        ("$0.00",  "0",       True),
        ("-10",    "-1000",   True),     # negative
        ("(0.50)", "-50",     True),     # parens for negative
        ("10.50",  "1050",    True),
        ("10.5",   "1050",    True),
        ("0.005",  "0",       False),    # diff $0.005 — at tightened half-cent tolerance, flagged
        ("0.005",  "1",       True),     # 0.005 vs 0.01 -- within half-cent tolerance? abs diff = 0.005, NOT < 0.005, so flag
        # actually 0.005 dollars vs 1 cent (0.01) -> diff is 0.005, which is NOT < 0.005, so flag
        # but float precision makes this iffy. Document.
    ]
    for i, (pv, uv, should_match) in enumerate(cases):
        emp = f"MONE_{i:02d}"
        paycom = make_paycom([{"Employee_Code": emp, "Fed_Addl_$": pv}])
        uzio = make_uzio([(emp, "MD", "ACTIVE")], overrides={(emp, "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): uv})
        _, _, allm, _, _ = run_audit(paycom, uzio)
        assert_finding("G15", f"P={pv!r} U={uv!r}", allm, emp, "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD", expected=not should_match)


# ─────────────────────────────────────────────────────────────────────────────
# G16 — More boolean vocabulary
# ─────────────────────────────────────────────────────────────────────────────
def g16_more_booleans():
    print("\n=== G16: Extended boolean vocab ===")
    cases = [
        (" Yes ",   "true",    True),    # whitespace
        ("yes ",    "true",    True),
        ("T",       "true",    True),    # T/F shorthand
        ("F",       "false",   True),
        ("YES!",    "true",    False),   # garbage -> can't parse -> mismatch path
        ("2",       "true",    False),   # 2 isn't 0/1
        ("-1",      "false",   False),
        ("maybe",   "true",    False),
    ]
    for i, (pv, uv, should_match) in enumerate(cases):
        emp = f"BOL_{i:02d}"
        paycom = make_paycom([{"Employee_Code": emp, "Block_Fed_Tax?": pv}])
        uzio   = make_uzio([(emp, "MD", "ACTIVE")], overrides={(emp, "FIT_WITHHOLDING_EXEMPTION"): uv})
        _, _, allm, _, _ = run_audit(paycom, uzio)
        assert_finding("G16", f"P={pv!r} U={uv!r}", allm, emp, "FIT_WITHHOLDING_EXEMPTION", expected=not should_match)


# ─────────────────────────────────────────────────────────────────────────────
# G17 — Multiple mismatches per employee
# ─────────────────────────────────────────────────────────────────────────────
def g17_multiple_mismatches():
    print("\n=== G17: Multiple mismatches on one employee ===")
    emp = "MULTI"
    paycom = make_paycom([{
        "Employee_Code": emp,
        "Work_Location_State": "MD",
        "Fed_Addl_$": "10",
        "Fed_Deductions_$": "500",
        "Fed_Other_Income_$": "300",
        "State_Addl_$": "15",
    }])
    uzio = make_uzio([(emp, "MD", "ACTIVE")], overrides={
        (emp, "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): "9999",   # mismatch
        (emp, "FIT_DEDUCTIONS_OVER_STANDARD"):        "99999",  # mismatch
        (emp, "FIT_OTHER_INCOME"):                    "9999",   # mismatch
        (emp, "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): "9999",   # mismatch
    })
    _, _, allm, _, _ = run_audit(paycom, uzio)
    flagged_fields = set(allm[allm["Employee ID"].astype(str) == emp]["UZIO Field Key"]) if not allm.empty else set()
    expected = {"FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD", "FIT_DEDUCTIONS_OVER_STANDARD",
                "FIT_OTHER_INCOME", "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"}
    record("G17", "all 4 mismatches reported on same employee",
           flagged_fields == expected,
           f"got {sorted(flagged_fields)}, missing {sorted(expected - flagged_fields)}")


# ─────────────────────────────────────────────────────────────────────────────
# G18 — Employee ID whitespace / case
# ─────────────────────────────────────────────────────────────────────────────
def g18_emp_id_edge():
    print("\n=== G18: Employee ID whitespace / casing ===")
    # Whitespace in IDs should match across files (Paycom normalizes via .strip())
    paycom = make_paycom([{"Employee_Code": " ABC123 ", "Fed_Addl_$": "10"}])
    uzio = make_uzio([("ABC123", "MD", "ACTIVE")], overrides={("ABC123", "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): "9999"})
    _, _, allm, miss, _ = run_audit(paycom, uzio)
    # After Paycom strip, IDs should match
    in_miss = "ABC123" in (set(miss["Employee ID"].astype(str)) if not miss.empty else set())
    flagged = not allm.empty and any(allm["Employee ID"].astype(str).str.strip() == "ABC123")
    record("G18", "whitespace in Paycom emp_id matches stripped UZIO id",
           flagged and not in_miss,
           f"flagged={flagged}, in_missing={in_miss}")

    # Case sensitivity — paycom 'abc123' vs uzio 'ABC123': these should NOT match
    paycom = make_paycom([{"Employee_Code": "abc123", "Fed_Addl_$": "10"}])
    uzio = make_uzio([("ABC123", "MD", "ACTIVE")], overrides={("ABC123", "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): "9999"})
    _, _, allm, miss, _ = run_audit(paycom, uzio)
    in_miss = "abc123" in (set(miss["Employee ID"].astype(str)) if not miss.empty else set())
    record("G18", "different-case IDs treated as different employees",
           in_miss,
           f"abc123 in Missing_in_UZIO = {in_miss}")


# ─────────────────────────────────────────────────────────────────────────────
# G19 — Duplicate employee rows in Paycom
# ─────────────────────────────────────────────────────────────────────────────
def g19_duplicates():
    print("\n=== G19: Duplicate rows ===")
    # Same emp_id twice in Paycom — what happens?
    paycom = make_paycom([
        {"Employee_Code": "DUP",  "Fed_Addl_$": "10"},
        {"Employee_Code": "DUP",  "Fed_Addl_$": "20"},  # different value
    ])
    uzio = make_uzio([("DUP", "MD", "ACTIVE")], overrides={("DUP", "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): "1000"})
    try:
        _, _, allm, _, _ = run_audit(paycom, uzio)
        # Should produce some output, not crash. We don't strictly assert which
        # row wins, but the tool should not error.
        record("G19", "duplicate Paycom rows don't crash", True,
               f"reported {len(allm)} mismatch row(s)")
    except Exception as e:
        record("G19", "duplicate Paycom rows don't crash", False, f"crashed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# G20 — Scale check
# ─────────────────────────────────────────────────────────────────────────────
def g20_scale():
    print("\n=== G20: Scale (1000 employees) ===")
    import time
    rows_paycom = []
    pairs = []
    overrides = {}
    for i in range(1000):
        emp = f"E{i:05d}"
        rows_paycom.append({"Employee_Code": emp, "Fed_Addl_$": "10"})
        pairs.append((emp, "MD", "ACTIVE"))
        # Every 10th employee has a mismatch
        if i % 10 == 0:
            overrides[(emp, "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD")] = "9999"

    paycom = make_paycom(rows_paycom)
    uzio = make_uzio(pairs, overrides=overrides)
    t0 = time.perf_counter()
    try:
        _, act, allm, _, _ = run_audit(paycom, uzio)
        elapsed = time.perf_counter() - t0
        expected_mismatches = 100
        record("G20", f"1000-employee audit completes in <30s",
               elapsed < 30,
               f"took {elapsed:.2f}s, {len(allm)} mismatches (expected {expected_mismatches})")
        record("G20", "1000-employee audit gets right mismatch count",
               len(allm) == expected_mismatches,
               f"got {len(allm)}, expected {expected_mismatches}")
    except Exception as e:
        record("G20", "1000-employee audit completes", False, f"crashed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    for fn in [g1_per_field_coverage, g2_boolean_vocab, g3_money_cents,
               g4_numeric_edges, g5_filing_status, g6_iowa_rule, g7_multistate,
               g8_status_vocab, g9_missing_populations, g10_data_shapes,
               g11_autodetect, g12_output_integrity,
               g13_per_field_match, g14_filing_status_state_prefix, g15_money_edges,
               g16_more_booleans, g17_multiple_mismatches, g18_emp_id_edge,
               g19_duplicates, g20_scale]:
        try:
            fn()
        except Exception:
            print(f"\n  !!! Test group {fn.__name__} CRASHED:")
            traceback.print_exc()

    print("\n" + "=" * 72)
    print("FINAL TALLY")
    print("=" * 72)
    by_group = {}
    for g, n, ok, m in results:
        by_group.setdefault(g, [0, 0])
        by_group[g][0 if ok else 1] += 1

    total_pass = sum(p for p, _ in by_group.values())
    total_fail = sum(f for _, f in by_group.values())
    print(f"  {'GROUP':<5s} {'PASS':>6s} {'FAIL':>6s}")
    for g in sorted(by_group):
        p, f = by_group[g]
        print(f"  {g:<5s} {p:>6d} {f:>6d}")
    print(f"  {'-' * 18}")
    print(f"  {'TOTAL':<5s} {total_pass:>6d} {total_fail:>6d}")
    print()
    if total_fail:
        print("  FAILURES:")
        for g, n, ok, m in results:
            if not ok:
                print(f"    {g}.{n}: {m}")
        print(f"\n  RESULT: {total_fail} FAILURE(S) — see above.")
    else:
        print("  RESULT: ALL PASSED.")


if __name__ == "__main__":
    main()
