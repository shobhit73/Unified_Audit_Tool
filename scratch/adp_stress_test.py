"""No-leniency stress test suite for the ADP withholding audit (v3 rebuild).

Same depth / discipline as scratch/paycom_stress_test.py, adapted to ADP's
richer architecture: Category column (Mismatch / Blank vs Value / Needs UI
Verification), multi-state SIT join, reciprocity sheet, stale UZIO records,
no-SIT-state filtering, SIT_FILING_STATUS auto-skip for states like MA, W-4
history dedup, file auto-detection.

Run:
    python scratch/adp_stress_test.py
"""

from __future__ import annotations
import sys, os, traceback, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from apps.adp.withholding_audit import (
    AuditOptions, run_audit, build_workbook,
    detect_source, compare_field, _resolve_repo_file,
    load_filing_status_map, load_key_mapping_yml, field_label,
    FILING_STATUS_MAP_FALLBACK, NO_SIT_STATES,
    CAT_MISMATCH, CAT_BLANK_VS_V, CAT_UI_VERIFY,
)


PASS = "[PASS]"
FAIL = "[FAIL]"
results = []   # (group, name, ok, message)


def record(group: str, name: str, ok: bool, message: str = ""):
    results.append((group, name, ok, message))
    tag = PASS if ok else FAIL
    print(f"  {tag} {group}.{name:<60s} {message}")


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic fixtures: ADP (wide) + UZIO (long)
# ─────────────────────────────────────────────────────────────────────────────

# Every field in the ADP wide format the tool can look at.
ADP_DEFAULTS = {
    "Associate ID":                                  "DEFAULT",
    "Legal First Name":                              "Test",
    "Legal Last Name":                               "Employee",
    "Federal/W4 Marital Status Description":         "Single or Married filing separately",
    "Federal Additional Tax Amount":                 "10",
    "Federal/W4 Exemptions":                         "0",
    "Dependents":                                    "2000",
    "Deductions":                                    "500",
    "Multiple Jobs indicator":                       "No",
    "Other Income":                                  "300",
    "Non-Resident Alien":                            "No",
    "Do Not Calculate Federal Income Tax":           "No",
    "Do not calculate State Tax":                    "No",
    "State Marital Status Description":              "Single",
    "State Exemptions/Allowances":                   "2",
    "State Additional Tax Amount":                   "15",
    "Federal/W4 Effective Date":                     "2026-01-01",
    "Worked in State Code":                          "MD",
    "Lived in State Code":                           "MD",
}

# Every UZIO field key the tool maps to, with its scope (FEDERAL vs STATE) and
# the matching default value (in UZIO storage form: cents for money fields,
# true/false for booleans, state-prefixed enum for filing status).
UZIO_DEFAULTS = {
    "FIT_WITHHOLDING_EXEMPTION":          ("false",                       "FEDERAL"),
    "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD":("1000",                        "FEDERAL"),
    "FIT_FILING_STATUS":                  ("FEDERAL_SINGLE_OR_MARRIED",   "FEDERAL"),
    "FIT_CHILD_AND_DEPENDENT_TAX_CREDIT": ("200000",                      "FEDERAL"),
    "FIT_DEDUCTIONS_OVER_STANDARD":       ("50000",                       "FEDERAL"),
    "FIT_HIGHER_WITHHOLDING":             ("false",                       "FEDERAL"),
    "FIT_OTHER_INCOME":                   ("30000",                       "FEDERAL"),
    "FIT_WITHHOLD_AS_NON_RESIDENT":       ("false",                       "FEDERAL"),
    "FIT_WITHHOLDING_ALLOWANCE":          ("0",                           "FEDERAL"),
    "SIT_WITHHOLDING_EXEMPTION":          ("false",                       "STATE"),
    "SIT_FILING_STATUS":                  ("MD_SINGLE",                   "STATE"),
    "SIT_TOTAL_ALLOWANCES":               ("2",                           "STATE"),
    "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD":("1500",                        "STATE"),
}


def make_adp(rows):
    """Build an ADP wide DataFrame. Each input row is a partial dict merged
    into the matching default."""
    out = []
    cols = list(ADP_DEFAULTS.keys())
    for r in rows:
        merged = dict(ADP_DEFAULTS)
        merged.update(r)
        out.append(merged)
        for k in r.keys():
            if k not in cols:
                cols.append(k)
    return pd.DataFrame(out, columns=cols)


def make_uzio(emp_state_pairs, overrides=None, extra_rows=None):
    """Build a UZIO long-format DataFrame.

    emp_state_pairs : list of (employee_id, work_state, status, eff_date) tuples.
    overrides       : {(emp_id, uzio_field_key): value} to override defaults.
    extra_rows      : list of full row dicts to append (for tests needing
                       custom field_keys outside the 13-mapping set).
    """
    overrides = overrides or {}
    rows = []
    for entry in emp_state_pairs:
        if len(entry) == 3:
            emp, st, status = entry
            eff = "2026-01-01"
        else:
            emp, st, status, eff = entry
        for uz_key, (default_val, scope) in UZIO_DEFAULTS.items():
            value = overrides.get((emp, uz_key), default_val)
            is_sit = scope == "STATE"
            rows.append({
                "employee_id":             emp,
                "employee_first_name":     "Test",
                "employee_last_name":      "Employee",
                "tax_scope":               scope,
                "state_code":              st if is_sit else "",
                "master_tax_type":         "STATE_INCOME_TAX" if is_sit else "FEDERAL_INCOME_TAX",
                "withholding_field_key":   uz_key,
                "withholding_field_value": value,
                "effective_date":          eff,
                "additional_info":         "",
                "status":                  status,
            })
    if extra_rows:
        rows.extend(extra_rows)
    return pd.DataFrame(rows)


def run(adp_df, uzio_df, options=None):
    return run_audit(adp_df, uzio_df, options or AuditOptions())


# ─────────────────────────────────────────────────────────────────────────────
# Assertion helpers
# ─────────────────────────────────────────────────────────────────────────────

def find_mismatch(out, emp_id, field_key=None, category=None):
    df = out.mismatches
    if df.empty:
        return df
    sub = df[df["EMPLOYEE_ID"].astype(str) == emp_id]
    if field_key:
        sub = sub[sub["FIELD_KEY"].astype(str) == field_key]
    if category:
        sub = sub[sub["CATEGORY"].astype(str) == category]
    return sub


def assert_finding(group, name, out, emp_id, field_key=None, expected=True, category=None):
    sub = find_mismatch(out, emp_id, field_key, category)
    found = not sub.empty
    if expected and found:
        info = ", ".join(f"{r['FIELD_KEY']}[{r['CATEGORY']}](P={r['ADP_VALUE_RAW']!r} U={r['UZIO_VALUE_RAW']!r})" for _, r in sub.iterrows())
        record(group, name, True, f"flagged: {info}")
    elif expected and not found:
        record(group, name, False, "expected mismatch, none found")
    elif not expected and found:
        info = ", ".join(f"{r['FIELD_KEY']}[{r['CATEGORY']}]" for _, r in sub.iterrows())
        record(group, name, False, f"UNEXPECTED finding: {info}")
    else:
        record(group, name, True, "correctly silent")


# ─────────────────────────────────────────────────────────────────────────────
# G1 — Per-field MISMATCH coverage
# ─────────────────────────────────────────────────────────────────────────────
def g1_per_field_mismatch():
    print("\n=== G1: Per-field mismatch (every mapped field, one at a time) ===")
    cases = [
        ("FIT_WITHHOLDING_EXEMPTION",            "Do Not Calculate Federal Income Tax",  "No",   "true"),
        ("FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD",  "Federal Additional Tax Amount",        "10",   "9999"),
        ("FIT_FILING_STATUS",                    "Federal/W4 Marital Status Description","Single or Married filing separately", "FEDERAL_HEAD_OF_HOUSEHOLD"),
        ("FIT_CHILD_AND_DEPENDENT_TAX_CREDIT",   "Dependents",                           "2000", "99999"),
        ("FIT_DEDUCTIONS_OVER_STANDARD",         "Deductions",                           "500",  "12345"),
        ("FIT_HIGHER_WITHHOLDING",               "Multiple Jobs indicator",              "No",   "true"),
        ("FIT_OTHER_INCOME",                     "Other Income",                         "300",  "9999"),
        ("FIT_WITHHOLD_AS_NON_RESIDENT",         "Non-Resident Alien",                   "No",   "true"),
        ("FIT_WITHHOLDING_ALLOWANCE",            "Federal/W4 Exemptions",                "0",    "5"),
        ("SIT_FILING_STATUS",                    "State Marital Status Description",     "Single", "MD_MARRIED"),
        ("SIT_TOTAL_ALLOWANCES",                 "State Exemptions/Allowances",          "2",    "9"),
        ("SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD",  "State Additional Tax Amount",          "15",   "9999"),
    ]
    for uz_key, adp_col, adp_val, uz_val in cases:
        emp = f"F1_{uz_key[:24]}"
        adp = make_adp([{"Associate ID": emp, adp_col: adp_val, "Worked in State Code": "MD"}])
        uzio = make_uzio([(emp, "MD", "ACTIVE")], overrides={(emp, uz_key): uz_val})
        out = run(adp, uzio)
        assert_finding("G1", uz_key, out, emp, uz_key, expected=True)

    # SIT_WITHHOLDING_EXEMPTION routes to UI Verification (intentional).
    emp = "F1_SIT_WH_EXEMPT"
    adp = make_adp([{"Associate ID": emp, "Do not calculate State Tax": "No", "Worked in State Code": "MD"}])
    uzio = make_uzio([(emp, "MD", "ACTIVE")], overrides={(emp, "SIT_WITHHOLDING_EXEMPTION"): "true"})
    out = run(adp, uzio)
    assert_finding("G1", "SIT_WITHHOLDING_EXEMPTION -> UI Verify", out, emp,
                   "SIT_WITHHOLDING_EXEMPTION", expected=True, category=CAT_UI_VERIFY)


# ─────────────────────────────────────────────────────────────────────────────
# G2 — Per-field MATCH (no false positives when values agree)
# ─────────────────────────────────────────────────────────────────────────────
def g2_per_field_match():
    print("\n=== G2: Per-field match (no false positives when values agree) ===")
    # Just run the baseline employee — every field at default — should produce 0 findings.
    emp = "F2_BASELINE"
    adp = make_adp([{"Associate ID": emp, "Worked in State Code": "MD", "Lived in State Code": "MD"}])
    uzio = make_uzio([(emp, "MD", "ACTIVE")])
    out = run(adp, uzio)
    sub = find_mismatch(out, emp)
    record("G2", "baseline employee produces 0 mismatches",
           sub.empty, f"got {len(sub)} mismatches: {sub['FIELD_KEY'].tolist() if not sub.empty else []}")


# ─────────────────────────────────────────────────────────────────────────────
# G3 — Boolean vocabulary
# ─────────────────────────────────────────────────────────────────────────────
def g3_boolean_vocab():
    print("\n=== G3: Boolean vocabulary ===")
    cases = [
        ("Yes","true",True), ("No","false",True), ("Y","true",True), ("N","false",True),
        ("1","true",True), ("0","false",True), ("yes","TRUE",True), ("YES","True",True),
        ("True","TRUE",True), ("on","true",True), ("off","false",True),
        ("Yes","false",False), ("No","true",False),
        ("","false",True),    # ADP treats blank as default false
        ("","true",False),    # ADP flags blank-vs-true as blank_vs_value
    ]
    for i, (pv, uv, should_match) in enumerate(cases):
        emp = f"B_{i:02d}"
        adp = make_adp([{"Associate ID": emp, "Do Not Calculate Federal Income Tax": pv,
                         "Worked in State Code": "MD"}])
        uzio = make_uzio([(emp, "MD", "ACTIVE")], overrides={(emp, "FIT_WITHHOLDING_EXEMPTION"): uv})
        out = run(adp, uzio)
        assert_finding("G3", f"P={pv!r} U={uv!r}", out, emp, "FIT_WITHHOLDING_EXEMPTION", expected=not should_match)


# ─────────────────────────────────────────────────────────────────────────────
# G4 — Money / cents conversion
# ─────────────────────────────────────────────────────────────────────────────
def g4_money_cents():
    print("\n=== G4: Money cents ===")
    cases = [
        ("0","0",True), ("10","1000",True), ("10.00","1000",True),
        ("$10","1000",True), ("1,000","100000",True),
        ("10","1001",False), ("10","999",False),
        ("","",True), ("","0",True), ("0","",True),
        ("10","",False), ("","1000",False),
        ("100000","10000000",True),
    ]
    for i, (pv, uv, should_match) in enumerate(cases):
        emp = f"M_{i:02d}"
        adp = make_adp([{"Associate ID": emp, "Federal Additional Tax Amount": pv,
                         "Worked in State Code": "MD"}])
        uzio = make_uzio([(emp, "MD", "ACTIVE")], overrides={(emp, "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): uv})
        out = run(adp, uzio)
        assert_finding("G4", f"P={pv!r} U={uv!r}", out, emp, "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD", expected=not should_match)


# ─────────────────────────────────────────────────────────────────────────────
# G5 — Numeric (FIT_WITHHOLDING_ALLOWANCE, SIT_TOTAL_ALLOWANCES)
# ─────────────────────────────────────────────────────────────────────────────
def g5_numeric():
    print("\n=== G5: Numeric (allowances) ===")
    cases = [
        ("0","0",True), ("1","1",True), ("","0",True), ("0","",True),
        ("2","5",False), ("99","100",False),
    ]
    for i, (pv, uv, should_match) in enumerate(cases):
        emp = f"N_{i:02d}"
        adp = make_adp([{"Associate ID": emp, "State Exemptions/Allowances": pv,
                         "Worked in State Code": "MD"}])
        uzio = make_uzio([(emp, "MD", "ACTIVE")], overrides={(emp, "SIT_TOTAL_ALLOWANCES"): uv})
        out = run(adp, uzio)
        assert_finding("G5", f"P={pv!r} U={uv!r}", out, emp, "SIT_TOTAL_ALLOWANCES", expected=not should_match)


# ─────────────────────────────────────────────────────────────────────────────
# G6 — Filing status matching
# ─────────────────────────────────────────────────────────────────────────────
def g6_filing_status():
    print("\n=== G6: Filing-status matching ===")
    cases = [
        ("Single",                            "MD_SINGLE",                True),
        ("Married",                           "MD_MARRIED",               True),
        ("single",                            "MD_SINGLE",                True),
        ("  Single  ",                        "MD_SINGLE",                True),
        ("Single",                            "MD_MARRIED",               False),
        ("Single or Married filing separately","FEDERAL_SINGLE_OR_MARRIED",True),
        ("",                                  "",                         True),
        ("Single",                            "",                         False),
        ("Single",                            "ZZ_UNKNOWN_ENUM",          False),
    ]
    for i, (pv, uv, should_match) in enumerate(cases):
        emp = f"FS_{i:02d}"
        adp = make_adp([{"Associate ID": emp, "State Marital Status Description": pv,
                         "Worked in State Code": "MD"}])
        uzio = make_uzio([(emp, "MD", "ACTIVE")], overrides={(emp, "SIT_FILING_STATUS"): uv})
        out = run(adp, uzio)
        assert_finding("G6", f"P={pv!r} U={uv!r}", out, emp, "SIT_FILING_STATUS", expected=not should_match)


# ─────────────────────────────────────────────────────────────────────────────
# G7 — Multi-state SIT join (employee with two states in UZIO)
# ─────────────────────────────────────────────────────────────────────────────
def g7_multistate():
    print("\n=== G7: Multi-state SIT ===")

    # Employee with UZIO records for both MD and NJ; ADP says they work in MD.
    # Comparison should run against MD only; NJ values should not contaminate.
    emp = "G7_MULTI"
    adp = make_adp([{"Associate ID": emp, "Worked in State Code": "MD",
                     "State Additional Tax Amount": "15"}])
    rows = []
    # MD record matches Paycom; NJ record doesn't.
    for st, addl in [("MD", "1500"), ("NJ", "9999")]:
        for uz_key, (val, scope) in UZIO_DEFAULTS.items():
            if scope == "STATE":
                v = addl if uz_key == "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD" else val
                rows.append({
                    "employee_id": emp, "employee_first_name": "Test", "employee_last_name": "Employee",
                    "tax_scope": "STATE", "state_code": st, "master_tax_type": "STATE_INCOME_TAX",
                    "withholding_field_key": uz_key, "withholding_field_value": v,
                    "effective_date": "2026-01-01", "additional_info": "", "status": "ACTIVE",
                })
        if st == "MD":  # add federal rows once
            for uz_key, (val, scope) in UZIO_DEFAULTS.items():
                if scope == "FEDERAL":
                    rows.append({
                        "employee_id": emp, "employee_first_name": "Test", "employee_last_name": "Employee",
                        "tax_scope": "FEDERAL", "state_code": "", "master_tax_type": "FEDERAL_INCOME_TAX",
                        "withholding_field_key": uz_key, "withholding_field_value": val,
                        "effective_date": "2026-01-01", "additional_info": "", "status": "ACTIVE",
                    })
    uzio = pd.DataFrame(rows)
    out = run(adp, uzio)
    assert_finding("G7", "MD work-state -> matched against MD record (no mismatch)",
                   out, emp, "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD", expected=False)

    # Now flip to NJ work-state. Should hit NJ record and mismatch ($15 vs $99.99).
    emp = "G7_MULTI_NJ"
    adp = make_adp([{"Associate ID": emp, "Worked in State Code": "NJ",
                     "State Additional Tax Amount": "15"}])
    # Reuse the same multi-state UZIO but adjust id
    rows2 = []
    for r in rows:
        r2 = dict(r); r2["employee_id"] = emp; rows2.append(r2)
    uzio = pd.DataFrame(rows2)
    out = run(adp, uzio)
    assert_finding("G7", "NJ work-state -> matched against NJ record (mismatch)",
                   out, emp, "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD", expected=True)


# ─────────────────────────────────────────────────────────────────────────────
# G8 — Reciprocity sheet (Lived ≠ Worked)
# ─────────────────────────────────────────────────────────────────────────────
def g8_reciprocity():
    print("\n=== G8: Reciprocity (Lived != Worked) ===")
    # Lived MI, Worked OH — reciprocity sheet should have a row regardless of mismatch.
    emp = "G8_REC"
    adp = make_adp([{"Associate ID": emp, "Worked in State Code": "OH", "Lived in State Code": "MI"}])
    uzio = make_uzio([(emp, "OH", "ACTIVE")])
    out = run(adp, uzio)
    has_rec = (not out.reciprocity.empty
               and emp in out.reciprocity["EMPLOYEE_ID"].astype(str).values)
    record("G8", "Lived MI / Worked OH -> reciprocity row", has_rec,
           f"reciprocity rows: {len(out.reciprocity)}")

    # Lived OH, Worked OH — no reciprocity row.
    emp = "G8_NOREC"
    adp = make_adp([{"Associate ID": emp, "Worked in State Code": "OH", "Lived in State Code": "OH"}])
    uzio = make_uzio([(emp, "OH", "ACTIVE")])
    out = run(adp, uzio)
    has_rec = (not out.reciprocity.empty
               and emp in out.reciprocity["EMPLOYEE_ID"].astype(str).values)
    record("G8", "Lived OH / Worked OH -> NO reciprocity row", not has_rec,
           f"reciprocity rows: {len(out.reciprocity)}")


# ─────────────────────────────────────────────────────────────────────────────
# G9 — Stale UZIO record detection
# ─────────────────────────────────────────────────────────────────────────────
def g9_stale_uzio():
    print("\n=== G9: Stale UZIO record detection ===")
    # ADP W-4 dated 2026-06-01; UZIO field eff dated 2024-01-01 -> stale.
    emp = "G9_STALE"
    adp = make_adp([{"Associate ID": emp, "Worked in State Code": "MD",
                     "Federal/W4 Effective Date": "2026-06-01"}])
    uzio = make_uzio([(emp, "MD", "ACTIVE", "2024-01-01")])
    out = run(adp, uzio)
    stale_rows = out.stale_uzio[out.stale_uzio["EMPLOYEE_ID"].astype(str) == emp] if not out.stale_uzio.empty else pd.DataFrame()
    record("G9", "ADP W-4 newer than UZIO eff_date -> stale flagged",
           not stale_rows.empty, f"stale rows for emp: {len(stale_rows)}")

    # UZIO newer than ADP -> NOT stale.
    emp = "G9_FRESH"
    adp = make_adp([{"Associate ID": emp, "Worked in State Code": "MD",
                     "Federal/W4 Effective Date": "2024-01-01"}])
    uzio = make_uzio([(emp, "MD", "ACTIVE", "2026-06-01")])
    out = run(adp, uzio)
    stale_rows = out.stale_uzio[out.stale_uzio["EMPLOYEE_ID"].astype(str) == emp] if not out.stale_uzio.empty else pd.DataFrame()
    record("G9", "UZIO eff_date newer than ADP W-4 -> NOT stale",
           stale_rows.empty, f"stale rows for emp: {len(stale_rows)}")


# ─────────────────────────────────────────────────────────────────────────────
# G10 — No-SIT states (FL, TX, NV, WA, WY, SD, AK, TN, NH)
# ─────────────────────────────────────────────────────────────────────────────
def g10_no_sit_states():
    print("\n=== G10: No-SIT states ===")
    for st in sorted(NO_SIT_STATES):
        emp = f"G10_{st}"
        adp = make_adp([{"Associate ID": emp, "Worked in State Code": st,
                         "State Additional Tax Amount": "99",
                         "State Marital Status Description": "Single"}])
        uzio = make_uzio([(emp, st, "ACTIVE")],
                          overrides={(emp, "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): "9999",
                                     (emp, "SIT_FILING_STATUS"): "MD_MARRIED"})
        out = run(adp, uzio)
        sit_mismatches = find_mismatch(out, emp, "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD")
        in_filtered = (not out.false_positives_filtered.empty
                       and emp in out.false_positives_filtered["EMPLOYEE_ID"].astype(str).values)
        record("G10", f"{st} (no-SIT state) -> SIT skipped, logged in filtered",
               sit_mismatches.empty and in_filtered,
               f"mismatches={len(sit_mismatches)}, in_filtered={in_filtered}")


# ─────────────────────────────────────────────────────────────────────────────
# G11 — SIT_FILING_STATUS auto-skip when UZIO has no such records
# ─────────────────────────────────────────────────────────────────────────────
def g11_sit_fs_autoskip():
    print("\n=== G11: SIT_FILING_STATUS auto-skip (MA pattern) ===")
    # Employee in MA: UZIO has no SIT_FILING_STATUS record for them (MA uses SIT_HOH).
    # ADP has "Single - Head of Household". Tool should NOT flag mismatch; should
    # log a False Positive Filtered row.
    emp = "G11_MA"
    adp = make_adp([{"Associate ID": emp, "Worked in State Code": "MA",
                     "State Marital Status Description": "Single - Head of Household"}])
    # UZIO: emit SIT rows but DON'T include SIT_FILING_STATUS for MA.
    rows = []
    for uz_key, (val, scope) in UZIO_DEFAULTS.items():
        if uz_key == "SIT_FILING_STATUS":
            continue
        is_sit = scope == "STATE"
        rows.append({
            "employee_id": emp, "employee_first_name": "Test", "employee_last_name": "Employee",
            "tax_scope": scope, "state_code": "MA" if is_sit else "",
            "master_tax_type": "STATE_INCOME_TAX" if is_sit else "FEDERAL_INCOME_TAX",
            "withholding_field_key": uz_key, "withholding_field_value": val,
            "effective_date": "2026-01-01", "additional_info": "", "status": "ACTIVE",
        })
    uzio = pd.DataFrame(rows)
    out = run(adp, uzio)
    sit_fs_mismatch = find_mismatch(out, emp, "SIT_FILING_STATUS")
    in_filtered = (not out.false_positives_filtered.empty
                   and ((out.false_positives_filtered["EMPLOYEE_ID"].astype(str) == emp)
                        & (out.false_positives_filtered["FIELD_KEY"] == "SIT_FILING_STATUS")).any())
    record("G11", "MA SIT_FILING_STATUS auto-skipped to filtered sheet",
           sit_fs_mismatch.empty and in_filtered,
           f"mismatch={len(sit_fs_mismatch)}, in_filtered={in_filtered}")


# ─────────────────────────────────────────────────────────────────────────────
# G12 — Category routing (Mismatch / Blank vs Value / Needs UI Verification)
# ─────────────────────────────────────────────────────────────────────────────
def g12_categories():
    print("\n=== G12: Category routing ===")

    # Mismatch — populated-vs-populated disagree.
    emp = "G12_M"
    adp = make_adp([{"Associate ID": emp, "Federal Additional Tax Amount": "10",
                     "Worked in State Code": "MD"}])
    uzio = make_uzio([(emp, "MD", "ACTIVE")], overrides={(emp, "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): "9999"})
    out = run(adp, uzio)
    assert_finding("G12", "populated-vs-populated -> Mismatch",
                   out, emp, "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD", expected=True, category=CAT_MISMATCH)

    # Blank vs Value — UZIO has non-zero, ADP blank.
    emp = "G12_BVV"
    adp = make_adp([{"Associate ID": emp, "Federal Additional Tax Amount": "",
                     "Worked in State Code": "MD"}])
    uzio = make_uzio([(emp, "MD", "ACTIVE")], overrides={(emp, "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): "9999"})
    out = run(adp, uzio)
    assert_finding("G12", "blank-vs-non-zero -> Blank vs Value",
                   out, emp, "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD", expected=True, category=CAT_BLANK_VS_V)

    # Needs UI Verification — SIT_WITHHOLDING_EXEMPTION disagree.
    emp = "G12_UI"
    adp = make_adp([{"Associate ID": emp, "Do not calculate State Tax": "Yes",
                     "Worked in State Code": "MD"}])
    uzio = make_uzio([(emp, "MD", "ACTIVE")], overrides={(emp, "SIT_WITHHOLDING_EXEMPTION"): "false"})
    out = run(adp, uzio)
    assert_finding("G12", "SIT_WITHHOLDING_EXEMPTION -> Needs UI Verification",
                   out, emp, "SIT_WITHHOLDING_EXEMPTION", expected=True, category=CAT_UI_VERIFY)


# ─────────────────────────────────────────────────────────────────────────────
# G13 — W-4 history dedup (ADP has multiple rows for one employee)
# ─────────────────────────────────────────────────────────────────────────────
def g13_w4_history():
    print("\n=== G13: W-4 history dedup ===")
    # Two ADP rows: older (2024) and newer (2026). Tool should use newer.
    emp = "G13_W4"
    adp = make_adp([
        {"Associate ID": emp, "Federal Additional Tax Amount": "999",
         "Federal/W4 Effective Date": "2024-01-01", "Worked in State Code": "MD"},
        {"Associate ID": emp, "Federal Additional Tax Amount": "10",
         "Federal/W4 Effective Date": "2026-01-01", "Worked in State Code": "MD"},
    ])
    uzio = make_uzio([(emp, "MD", "ACTIVE")])  # UZIO has 1000 cents = $10 (matches newer)
    out = run(adp, uzio)
    mm = find_mismatch(out, emp, "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD")
    record("G13", "newer ADP W-4 row wins (no mismatch)",
           mm.empty, f"mismatches: {len(mm)}")

    # W-4 history sheet should record BOTH rows (one marked as latest).
    history = out.w4_history
    emp_rows = history[history["Associate ID"].astype(str) == emp] if "Associate ID" in history.columns else pd.DataFrame()
    record("G13", "history sheet records both ADP rows",
           len(emp_rows) == 2, f"got {len(emp_rows)} rows")


# ─────────────────────────────────────────────────────────────────────────────
# G14 — Status from UZIO (Active vs Terminated routing)
# ─────────────────────────────────────────────────────────────────────────────
def g14_status_from_uzio():
    print("\n=== G14: Status from UZIO routing ===")
    # ADP has no status column — UZIO ACTIVE -> Active sheet.
    emp = "G14_ACT"
    adp = make_adp([{"Associate ID": emp, "Federal Additional Tax Amount": "10",
                     "Worked in State Code": "MD"}])
    uzio = make_uzio([(emp, "MD", "ACTIVE")], overrides={(emp, "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): "9999"})
    out = run(adp, uzio)
    mm = find_mismatch(out, emp, "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD")
    status = mm["EMPLOYMENT_STATUS"].iloc[0] if not mm.empty else ""
    record("G14", "UZIO ACTIVE -> EMPLOYMENT_STATUS=ACTIVE", status == "ACTIVE", f"got {status!r}")

    # UZIO TERMINATED -> Terminated.
    emp = "G14_TERM"
    adp = make_adp([{"Associate ID": emp, "Federal Additional Tax Amount": "10",
                     "Worked in State Code": "MD"}])
    uzio = make_uzio([(emp, "MD", "TERMINATED")], overrides={(emp, "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): "9999"})
    out = run(adp, uzio)
    mm = find_mismatch(out, emp, "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD")
    status = mm["EMPLOYMENT_STATUS"].iloc[0] if not mm.empty else ""
    record("G14", "UZIO TERMINATED -> EMPLOYMENT_STATUS=TERMINATED", status == "TERMINATED", f"got {status!r}")


# ─────────────────────────────────────────────────────────────────────────────
# G15 — File auto-detection
# ─────────────────────────────────────────────────────────────────────────────
def g15_detect_source():
    print("\n=== G15: File source auto-detection ===")
    uzio = make_uzio([("X", "MD", "ACTIVE")])
    adp  = make_adp([{"Associate ID": "X"}])
    record("G15", "UZIO long-format detected as 'uzio'", detect_source(uzio) == "uzio", f"got {detect_source(uzio)!r}")
    record("G15", "ADP wide-format detected as 'adp'",   detect_source(adp) == "adp",   f"got {detect_source(adp)!r}")
    record("G15", "random df detected as 'unknown'",     detect_source(pd.DataFrame({"foo": [1]})) == "unknown",
           "ok")


# ─────────────────────────────────────────────────────────────────────────────
# G16 — Missing populations
# ─────────────────────────────────────────────────────────────────────────────
def g16_missing_populations():
    print("\n=== G16: Missing populations ===")
    adp = make_adp([{"Associate ID": "BOTH"}, {"Associate ID": "ADPONLY"}])
    uzio = make_uzio([("BOTH", "MD", "ACTIVE"), ("UZIOONLY", "MD", "ACTIVE")])
    out = run(adp, uzio)
    miss_uzio_ids = set(out.missing_in_uzio["ASSOCIATE_ID"].astype(str)) if not out.missing_in_uzio.empty else set()
    miss_adp_ids  = set(out.missing_in_adp["EMPLOYEE_ID"].astype(str)) if not out.missing_in_adp.empty else set()
    record("G16", "ADPONLY -> Missing_in_UZIO",  "ADPONLY" in miss_uzio_ids, f"got {miss_uzio_ids}")
    record("G16", "UZIOONLY -> Missing_in_ADP",  "UZIOONLY" in miss_adp_ids,  f"got {miss_adp_ids}")
    record("G16", "BOTH not in either missing sheet",
           "BOTH" not in miss_uzio_ids and "BOTH" not in miss_adp_ids, "ok")


# ─────────────────────────────────────────────────────────────────────────────
# G17 — Output integrity (sheets + columns)
# ─────────────────────────────────────────────────────────────────────────────
def g17_output_integrity():
    print("\n=== G17: Output integrity ===")
    adp = make_adp([{"Associate ID": "OUT1", "Federal Additional Tax Amount": "10",
                     "Worked in State Code": "MD"}])
    uzio = make_uzio([("OUT1", "MD", "ACTIVE")], overrides={("OUT1", "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): "9999"})
    out = run(adp, uzio)

    expected_cols = ["EMPLOYEE_ID", "EMPLOYEE_NAME", "EMPLOYMENT_STATUS", "STATE_CODE",
                     "JURISDICTION", "CATEGORY", "FIELD_LABEL", "FIELD_KEY",
                     "ADP_COLUMN", "UZIO_COLUMN", "ADP_VALUE_RAW", "UZIO_VALUE_RAW",
                     "ADP_VALUE_NORMALIZED", "UZIO_VALUE_NORMALIZED", "RULE_APPLIED",
                     "ADP_EFFECTIVE_DATE_USED", "HAS_W4_HISTORY", "VERIFY_IN_UI_FIRST"]
    missing = [c for c in expected_cols if c not in out.mismatches.columns]
    record("G17", "mismatches DataFrame has all expected columns",
           not missing, f"missing: {missing}" if missing else "ok")

    # Try the xlsx serialization.
    try:
        data = build_workbook(out)
        record("G17", "build_workbook returns valid xlsx bytes",
               len(data) > 5000, f"{len(data):,} bytes")
    except Exception as e:
        record("G17", "build_workbook returns valid xlsx bytes", False, f"crashed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# G18 — Money sign / format edges
# ─────────────────────────────────────────────────────────────────────────────
def g18_money_edges():
    print("\n=== G18: Money sign/format edges ===")
    cases = [
        ("0.00","0",True), ("-0","0",True), ("00","0",True),
        ("$0.00","0",True),
        ("-10","-1000",True), ("(0.50)","-50",True),
        ("10.50","1050",True), ("10.5","1050",True),
    ]
    for i, (pv, uv, should_match) in enumerate(cases):
        emp = f"ME_{i:02d}"
        adp = make_adp([{"Associate ID": emp, "Federal Additional Tax Amount": pv,
                         "Worked in State Code": "MD"}])
        uzio = make_uzio([(emp, "MD", "ACTIVE")], overrides={(emp, "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): uv})
        out = run(adp, uzio)
        assert_finding("G18", f"P={pv!r} U={uv!r}", out, emp, "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD", expected=not should_match)


# ─────────────────────────────────────────────────────────────────────────────
# G19 — Employee ID handling
# ─────────────────────────────────────────────────────────────────────────────
def g19_emp_id():
    print("\n=== G19: Employee ID edges ===")
    # Whitespace
    adp = make_adp([{"Associate ID": " ABC ", "Federal Additional Tax Amount": "10",
                     "Worked in State Code": "MD"}])
    uzio = make_uzio([("ABC", "MD", "ACTIVE")], overrides={("ABC", "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): "9999"})
    out = run(adp, uzio)
    mm = find_mismatch(out, "ABC", "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD")
    record("G19", "whitespace-trimmed Associate ID matches UZIO",
           not mm.empty, f"flagged: {len(mm)}")

    # Leading zeros preserved
    adp = make_adp([{"Associate ID": "001234", "Federal Additional Tax Amount": "10",
                     "Worked in State Code": "MD"}])
    uzio = make_uzio([("001234", "MD", "ACTIVE")], overrides={("001234", "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): "9999"})
    out = run(adp, uzio)
    mm = find_mismatch(out, "001234", "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD")
    record("G19", "leading-zero ID preserved through audit",
           not mm.empty, f"flagged: {len(mm)}")


# ─────────────────────────────────────────────────────────────────────────────
# G20 — Data shape edge cases
# ─────────────────────────────────────────────────────────────────────────────
def g20_data_shapes():
    print("\n=== G20: Data shape edges ===")
    # Empty ADP
    try:
        adp = pd.DataFrame(columns=list(ADP_DEFAULTS.keys()))
        uzio = make_uzio([("X", "MD", "ACTIVE")])
        out = run(adp, uzio)
        record("G20", "empty ADP file doesn't crash", True, f"missing in ADP: {len(out.missing_in_adp)}")
    except Exception as e:
        record("G20", "empty ADP file doesn't crash", False, f"crashed: {e}")

    # Empty UZIO
    try:
        adp = make_adp([{"Associate ID": "X", "Worked in State Code": "MD"}])
        uzio = pd.DataFrame(columns=["employee_id", "withholding_field_key", "withholding_field_value", "state_code"])
        out = run(adp, uzio)
        record("G20", "empty UZIO file doesn't crash", True,
               f"missing in UZIO: {len(out.missing_in_uzio)}")
    except Exception as e:
        record("G20", "empty UZIO file doesn't crash", False, f"crashed: {e}")

    # Blank Associate ID rows get filtered
    try:
        adp = make_adp([{"Associate ID": "", "Worked in State Code": "MD"},
                        {"Associate ID": "VALID", "Worked in State Code": "MD"}])
        uzio = make_uzio([("VALID", "MD", "ACTIVE")])
        out = run(adp, uzio)
        record("G20", "blank Associate ID rows ignored", True, "ok")
    except Exception as e:
        record("G20", "blank Associate ID rows ignored", False, f"crashed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# G21 — Filing-status loader (file + fallback merge)
# ─────────────────────────────────────────────────────────────────────────────
def g21_filing_status_loader():
    print("\n=== G21: filing status_code.txt loader ===")
    fs = load_filing_status_map()
    record("G21", "merged filing status map has hardcoded fallback entries",
           "FEDERAL_SINGLE" in fs and "MD_SINGLE" in fs, f"len={len(fs)}")
    record("G21", "merged size >= fallback size",
           len(fs) >= len(FILING_STATUS_MAP_FALLBACK), f"merged={len(fs)} fallback={len(FILING_STATUS_MAP_FALLBACK)}")

    # key_mapping.yml loader
    labels = load_key_mapping_yml()
    record("G21", "key_mapping.yml loaded as nested dict",
           isinstance(labels, dict) and "FED" in labels, f"jurisdictions={len(labels)}")
    record("G21", "FED has FIT_HIGHER_WITHHOLDING -> 'Multiple Jobs'",
           labels.get("FED", {}).get("FIT_HIGHER_WITHHOLDING") == "Multiple Jobs", "ok")


# ─────────────────────────────────────────────────────────────────────────────
# G22 — Scale check
# ─────────────────────────────────────────────────────────────────────────────
def g22_scale():
    print("\n=== G22: Scale (1000 employees) ===")
    adp_rows = []
    uzio_pairs = []
    overrides = {}
    for i in range(1000):
        emp = f"S{i:05d}"
        adp_rows.append({"Associate ID": emp, "Federal Additional Tax Amount": "10",
                         "Worked in State Code": "MD", "Lived in State Code": "MD"})
        uzio_pairs.append((emp, "MD", "ACTIVE"))
        if i % 10 == 0:
            overrides[(emp, "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD")] = "9999"
    adp = make_adp(adp_rows)
    uzio = make_uzio(uzio_pairs, overrides=overrides)
    t0 = time.perf_counter()
    try:
        out = run(adp, uzio)
        elapsed = time.perf_counter() - t0
        record("G22", f"1000-employee audit completes in <60s", elapsed < 60,
               f"took {elapsed:.2f}s; mismatches={len(out.mismatches)}")
        n_mm = int((out.mismatches["FIELD_KEY"] == "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD").sum()) if not out.mismatches.empty else 0
        record("G22", "1000-employee audit gets right mismatch count (100)",
               n_mm == 100, f"got {n_mm}")
    except Exception as e:
        record("G22", "1000-employee audit completes", False, f"crashed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# G23 — Stale UZIO check fires per-field, not per-employee
# ─────────────────────────────────────────────────────────────────────────────
def g23_stale_per_field():
    print("\n=== G23: Stale per-field granularity ===")
    # Mix per-field eff_dates: 2 stale fields, 2 fresh fields for same employee.
    emp = "G23"
    adp = make_adp([{"Associate ID": emp, "Worked in State Code": "MD",
                     "Federal/W4 Effective Date": "2026-06-01"}])
    rows = []
    for uz_key, (val, scope) in UZIO_DEFAULTS.items():
        # Half stale (2024), half fresh (2026-12)
        eff = "2024-01-01" if list(UZIO_DEFAULTS.keys()).index(uz_key) % 2 == 0 else "2026-12-01"
        is_sit = scope == "STATE"
        rows.append({
            "employee_id": emp, "employee_first_name": "Test", "employee_last_name": "Employee",
            "tax_scope": scope, "state_code": "MD" if is_sit else "",
            "master_tax_type": "STATE_INCOME_TAX" if is_sit else "FEDERAL_INCOME_TAX",
            "withholding_field_key": uz_key, "withholding_field_value": val,
            "effective_date": eff, "additional_info": "", "status": "ACTIVE",
        })
    uzio = pd.DataFrame(rows)
    out = run(adp, uzio)
    stale_for_emp = out.stale_uzio[out.stale_uzio["EMPLOYEE_ID"].astype(str) == emp] if not out.stale_uzio.empty else pd.DataFrame()
    # We expect roughly half the fields to be flagged stale.
    record("G23", "stale check fires per-field, not just per-employee",
           len(stale_for_emp) >= 3, f"stale rows: {len(stale_for_emp)}")


# ─────────────────────────────────────────────────────────────────────────────
# G24 — Configurability of AuditOptions
# ─────────────────────────────────────────────────────────────────────────────
def g24_options():
    print("\n=== G24: AuditOptions toggles ===")
    # With skip_no_sit_states=False, SIT for TX should compare and likely flag.
    emp = "G24"
    adp = make_adp([{"Associate ID": emp, "Worked in State Code": "TX",
                     "State Additional Tax Amount": "99"}])
    uzio = make_uzio([(emp, "TX", "ACTIVE")], overrides={(emp, "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"): "1500"})

    out_default = run(adp, uzio)  # default skips TX
    in_filtered = (not out_default.false_positives_filtered.empty
                   and emp in out_default.false_positives_filtered["EMPLOYEE_ID"].astype(str).values)
    record("G24", "skip_no_sit_states=True (default) -> TX in filtered",
           in_filtered, f"filtered: {in_filtered}")

    out_noskip = run(adp, uzio, AuditOptions(skip_no_sit_states=False))
    mm = find_mismatch(out_noskip, emp, "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD")
    record("G24", "skip_no_sit_states=False -> TX SIT compared (mismatch)",
           not mm.empty, f"mismatches: {len(mm)}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    for fn in [g1_per_field_mismatch, g2_per_field_match, g3_boolean_vocab,
               g4_money_cents, g5_numeric, g6_filing_status, g7_multistate,
               g8_reciprocity, g9_stale_uzio, g10_no_sit_states,
               g11_sit_fs_autoskip, g12_categories, g13_w4_history,
               g14_status_from_uzio, g15_detect_source, g16_missing_populations,
               g17_output_integrity, g18_money_edges, g19_emp_id, g20_data_shapes,
               g21_filing_status_loader, g22_scale, g23_stale_per_field, g24_options]:
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
    print(f"  {'GROUP':<6s} {'PASS':>6s} {'FAIL':>6s}")
    for g in sorted(by_group, key=lambda x: (len(x), x)):
        p, f = by_group[g]
        print(f"  {g:<6s} {p:>6d} {f:>6d}")
    print(f"  {'-' * 20}")
    print(f"  {'TOTAL':<6s} {total_pass:>6d} {total_fail:>6d}")
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
