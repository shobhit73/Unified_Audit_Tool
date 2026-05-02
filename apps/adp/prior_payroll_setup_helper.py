"""ADP - Prior Payroll Setup Helper Tool.

Discovers what to configure in Uzio for an ADP Prior Payroll migration.
Given a sanitized ADP Prior Payroll file plus the State Tax Code master CSV,
emits an Excel workbook with:

  - Earnings_Codes      - REGULAR / OVERTIME + every ADDITIONAL EARNINGS code
                          with $ total, employee count, paired hours, avg rate.
  - Contributions       - 401k / 403b / 457 / Roth / HSA / FSA voluntary codes.
  - Deductions          - all other voluntary deductions, with pre-tax vs
                          post-tax verdict per code.
  - Taxes_Discovered    - every '* - EMPLOYEE TAX' / '* - EMPLOYER TAX' column.
  - Tax_Mapping         - one row per (tax_type, state) in the
                          'Payroll_Mappings_Tax_Mapping_CORRECTED' format.
  - Bonus_Classification- FLSA test (discretionary vs non-discretionary).

Pre/post-tax algorithm:
  gap_FIT = TOTAL EARNINGS - FEDERAL INCOME - EMPLOYEE TAXABLE.
  Find any subset of a row's non-zero deductions summing to gap_FIT (within
  $0.02). Every member of any passing subset is pre-tax for FIT. ONE positive
  proof anywhere in the file = pre-tax for everyone (the rule never varies
  per employee). Same logic for FICA / MEDI / SIT taxables to derive the
  flavor: section_125 (pre-FIT/FICA/MEDI/SIT) vs 401k_traditional
  (pre-FIT/SIT only, NOT pre-FICA/MEDI).
"""

import io
import re
from itertools import combinations

import pandas as pd
import streamlit as st

from apps.adp.prior_payroll_sanity import read_input_file, _find_col
from utils.audit_utils import clean_money_val


# ---------- helpers ----------

def _num(v):
    try:
        return clean_money_val(v)
    except Exception:
        return 0.0


def _strip_prefix(col, prefixes):
    s = str(col).strip()
    for p in prefixes:
        if s.upper().startswith(p.upper()):
            rest = s[len(p):].lstrip(" :").strip()
            return rest
    return s


# ---------- column categorization ----------

EARN_PREFIXES = ["ADDITIONAL EARNINGS"]
HOUR_PREFIXES = ["ADDITIONAL HOURS"]
DED_PREFIX = "VOLUNTARY DEDUCTION"
MEMO_PREFIX = "MEMO"

CONTRIB_PATTERN = re.compile(
    r"\b(401[Kk]?|403[Bb]?|457|ROTH|HSA|FSA|RETIRE|RETIREMENT)\b"
)


def categorize_columns(df):
    earn_cols, hour_cols, tax_cols, taxable_cols = [], [], [], []
    ded_cols, memo_cols = [], []
    for c in df.columns:
        s = str(c).strip(); u = s.upper()
        if u in ("REGULAR EARNINGS", "OVERTIME EARNINGS"):
            earn_cols.append(c)
        elif u.startswith("ADDITIONAL EARNINGS"):
            earn_cols.append(c)
        elif u in ("REGULAR HOURS", "OVERTIME HOURS"):
            hour_cols.append(c)
        elif u.startswith("ADDITIONAL HOURS"):
            hour_cols.append(c)
        elif u.startswith(DED_PREFIX):
            ded_cols.append(c)
        elif u.startswith(MEMO_PREFIX):
            memo_cols.append(c)
        elif u.endswith("TAXABLE"):
            taxable_cols.append(c)
        elif u.endswith("EMPLOYEE TAX") or u.endswith("EMPLOYER TAX"):
            if u.startswith("TOTAL "):
                continue  # aggregate, not a real tax row
            tax_cols.append(c)
    return {
        "earnings": earn_cols, "hours": hour_cols,
        "taxes": tax_cols, "taxables": taxable_cols,
        "deductions": ded_cols, "memos": memo_cols,
    }


# ---------- catalog builders ----------

def build_earnings_catalog(df, earn_cols, hour_cols):
    hour_lookup = {}
    for h in hour_cols:
        u = str(h).strip().upper()
        if u == "REGULAR HOURS":
            hour_lookup["REGULAR EARNINGS"] = h
        elif u == "OVERTIME HOURS":
            hour_lookup["OVERTIME EARNINGS"] = h
        else:
            code = _strip_prefix(h, HOUR_PREFIXES)
            hour_lookup[f"ADDITIONAL EARNINGS  : {code}"] = h
            hour_lookup[code] = h

    rows = []
    for c in earn_cols:
        amounts = df[c].apply(_num)
        total = float(amounts.sum())
        emp_count = int((amounts != 0).sum())
        u = str(c).strip().upper()
        if u == "REGULAR EARNINGS":
            code = "REGULAR"; kind = "Regular Wage"
        elif u == "OVERTIME EARNINGS":
            code = "OVERTIME"; kind = "Overtime"
        else:
            code = _strip_prefix(c, EARN_PREFIXES); kind = "Additional Earning"

        h_col = hour_lookup.get(str(c).strip()) or hour_lookup.get(code)
        if h_col is not None and h_col in df.columns:
            hours_total = float(df[h_col].apply(_num).sum())
            avg_rate = total / hours_total if hours_total > 0 else None
        else:
            hours_total = None; avg_rate = None

        rows.append({
            "Source Column": str(c).strip(), "Code": code, "Kind": kind,
            "Total $": round(total, 2), "Employees": emp_count,
            "Total Hours": round(hours_total, 2) if hours_total is not None else None,
            "Avg Rate ($/hr)": round(avg_rate, 4) if avg_rate is not None else None,
        })
    return rows


# ---------- pre/post-tax classifier ----------

def _row_gap(row, total_earn_col, taxable_col):
    return _num(row.get(total_earn_col)) - _num(row.get(taxable_col))


def _subset_sum_match(amounts, target, tol=0.02):
    n = len(amounts)
    if n == 0:
        return []
    matches = []
    for r in range(1, n + 1):
        for combo in combinations(range(n), r):
            s = sum(amounts[i] for i in combo)
            if abs(s - target) <= tol:
                matches.append(combo)
    return matches


def _name_heuristic(col):
    u = str(col).upper()
    if any(t in u for t in ("SUPPORT", "GARN", "GARNISH", "LEVY", "LIEN", "CHILD")):
        return "post_tax", "garnishment", [], "name_heuristic"
    if any(t in u for t in ("ADVANCE", "ADV-", "LOAN", "REPAY", "TAPCHECK", "DAILY")):
        return "post_tax", "advance_or_loan", [], "name_heuristic"
    if any(t in u for t in ("REVERSE", "REV-", "REISSU")):
        return "post_tax", "corrective", [], "name_heuristic"
    if any(t in u for t in ("ROTH",)):
        return "post_tax", "roth", [], "name_heuristic"
    if any(t in u for t in ("MEDICAL", "MED-", "DENTAL", "DEN-", "VISION", "VIS-",
                            "HSA", "FSA")):
        return "pre_tax", "section_125", ["FIT", "FICA", "MEDI", "SIT"], "name_heuristic"
    if CONTRIB_PATTERN.search(u):
        return "pre_tax", "401k_traditional", ["FIT", "SIT"], "name_heuristic"
    return "post_tax", "default_unknown", [], "name_heuristic"


def classify_deductions_pretax(
    df, ded_cols, total_earn_col, fit_taxable_col, fica_taxable_col,
    medi_taxable_col, sit_taxable_col, tol=0.02, max_subset=8,
):
    proven = {c: {"FIT": False, "FICA": False, "MEDI": False, "SIT": False}
              for c in ded_cols}
    sample = {c: [] for c in ded_cols}

    def _try_axis(taxable_col, key):
        if taxable_col is None:
            return
        for _, row in df.iterrows():
            gap = _row_gap(row, total_earn_col, taxable_col)
            if gap <= tol:
                continue
            present = [(c, _num(row.get(c))) for c in ded_cols if _num(row.get(c)) > 0]
            if not present or len(present) > max_subset:
                continue
            cols = [c for c, _ in present]
            amts = [a for _, a in present]
            for combo in _subset_sum_match(amts, gap, tol):
                for i in combo:
                    proven[cols[i]][key] = True
                if key == "FIT":
                    eid = row.get("ASSOCIATE ID") or row.get("Associate ID")
                    for i in combo:
                        if len(sample[cols[i]]) < 3:
                            sample[cols[i]].append({
                                "associate": str(eid) if eid is not None else "",
                                "gap_fit": round(gap, 2),
                                "subset": [cols[j] for j in combo],
                                "subset_sum": round(sum(amts[j] for j in combo), 2),
                            })

    _try_axis(fit_taxable_col, "FIT")
    _try_axis(fica_taxable_col, "FICA")
    _try_axis(medi_taxable_col, "MEDI")
    _try_axis(sit_taxable_col, "SIT")

    rows = []
    for c in ded_cols:
        amounts = df[c].apply(_num)
        total = float(amounts.sum())
        emp_count = int((amounts != 0).sum())
        p = proven[c]
        if p["FIT"] and p["FICA"] and p["MEDI"]:
            verdict = "pre_tax"; flavor = "section_125"
            pre_taxes = ["FIT", "FICA", "MEDI"] + (["SIT"] if p["SIT"] else [])
        elif p["FIT"] and p["SIT"] and not p["FICA"]:
            verdict = "pre_tax"; flavor = "401k_traditional"; pre_taxes = ["FIT", "SIT"]
        elif p["FIT"] and not (p["FICA"] or p["MEDI"]):
            verdict = "pre_tax"; flavor = "pretax_unknown"; pre_taxes = ["FIT"]
        elif p["FIT"] or p["FICA"] or p["MEDI"] or p["SIT"]:
            verdict = "pre_tax"; flavor = "mixed_unusual"
            pre_taxes = [k for k in ("FIT", "FICA", "MEDI", "SIT") if p[k]]
        else:
            verdict = "post_tax"; flavor = ""; pre_taxes = []

        if emp_count == 0:
            verdict, flavor, pre_taxes, confidence = _name_heuristic(c)
        else:
            confidence = "empirical_subset_sum"

        code = _strip_prefix(c, [DED_PREFIX])
        is_contrib = bool(CONTRIB_PATTERN.search(code.upper()))
        rows.append({
            "Source Column": str(c).strip(), "Code": code,
            "Total $": round(total, 2), "Employees": emp_count,
            "Verdict": verdict, "Pre-Tax Of": ",".join(pre_taxes),
            "Pre-Tax Flavor": flavor, "Confidence": confidence,
            "Sample": "; ".join(
                f"{s['associate']}: gap={s['gap_fit']}, subset_sum={s['subset_sum']}"
                for s in sample[c][:2]
            ),
            "_is_contribution": is_contrib,
        })
    return rows


# ---------- bonus classifier (FLSA) ----------

def classify_bonus(df, earn_cols):
    reg_e = _find_col(df, ["REGULAR EARNINGS"])
    reg_h = _find_col(df, ["REGULAR HOURS"])
    ot_e = _find_col(df, ["OVERTIME EARNINGS"])
    ot_h = _find_col(df, ["OVERTIME HOURS"])

    bonus_cols = []
    for c in earn_cols:
        u = str(c).upper()
        code = _strip_prefix(c, EARN_PREFIXES).upper()
        if "BONUS" in u or re.search(r"\bBN[A-Z0-9]*\b", code) or code.startswith("BN"):
            if "BACKUP" in u or code.startswith("BCK"):
                continue
            bonus_cols.append(c)

    if not bonus_cols or not (reg_e and reg_h and ot_e and ot_h):
        return {
            "verdict": "indeterminate",
            "reason": "Missing bonus / overtime columns to test",
            "bonus_columns_found": [str(c) for c in bonus_cols],
            "rows_tested": 0, "discretionary_rows": 0, "non_discretionary_rows": 0,
            "samples": [],
        }

    rows_tested = 0; discretionary_rows = 0; non_disc_rows = 0
    samples = []
    rate_tol_pct = 0.005

    for _, r in df.iterrows():
        bonus_amt = sum(_num(r.get(c)) for c in bonus_cols)
        re_v = _num(r.get(reg_e)); rh_v = _num(r.get(reg_h))
        oe_v = _num(r.get(ot_e)); oh_v = _num(r.get(ot_h))
        if bonus_amt <= 0 or oh_v <= 0 or rh_v <= 0 or re_v <= 0:
            continue
        rows_tested += 1
        regular_rate = re_v / rh_v
        expected_ot_rate = 1.5 * regular_rate
        actual_ot_rate = oe_v / oh_v
        diff_pct = (actual_ot_rate - expected_ot_rate) / expected_ot_rate

        verdict_row = "discretionary"
        if diff_pct > rate_tol_pct:
            verdict_row = "non_discretionary"; non_disc_rows += 1
        else:
            discretionary_rows += 1

        if len(samples) < 5:
            eid = r.get("ASSOCIATE ID") or r.get("Associate ID")
            samples.append({
                "associate": str(eid) if eid is not None else "",
                "regular_earnings": round(re_v, 2), "regular_hours": round(rh_v, 4),
                "regular_rate": round(regular_rate, 4),
                "expected_ot_rate_1.5x": round(expected_ot_rate, 4),
                "actual_ot_rate": round(actual_ot_rate, 4),
                "diff_pct": round(diff_pct * 100, 3),
                "bonus_amt": round(bonus_amt, 2), "verdict_row": verdict_row,
            })

    if rows_tested == 0:
        verdict = "indeterminate"
        reason = "No row had both bonus and overtime hours"
    elif non_disc_rows > 0:
        verdict = "non_discretionary"
        reason = (
            f"{non_disc_rows} of {rows_tested} rows show actual OT rate "
            f"materially above 1.5 x regular rate => bonus inflated regular rate => "
            f"non-discretionary (any positive proof is conclusive under FLSA)."
        )
    else:
        verdict = "discretionary"
        reason = (
            f"All {rows_tested} rows show actual OT rate ~ 1.5 x regular rate => "
            f"bonus did not inflate the regular rate basis => discretionary."
        )

    return {
        "verdict": verdict, "reason": reason,
        "bonus_columns_found": [str(c) for c in bonus_cols],
        "rows_tested": rows_tested,
        "discretionary_rows": discretionary_rows,
        "non_discretionary_rows": non_disc_rows,
        "samples": samples,
    }


# ---------- tax mapping ----------

TAX_TOKEN_MAP = {
    "FEDERAL INCOME - EMPLOYEE TAX":          ("FED", "FIT"),
    "MEDICARE - EMPLOYEE TAX":                ("FED", "MEDI"),
    "MEDICARE - EMPLOYER TAX":                ("FED", "ER_MEDI"),
    "SOCIAL SECURITY - EMPLOYEE TAX":         ("FED", "FICA"),
    "SOCIAL SECURITY - EMPLOYER TAX":         ("FED", "ER_FICA"),
    "FUTA - EMPLOYER TAX":                    ("FED", "ER_FUTA"),
    "WORKED IN STATE - EMPLOYEE TAX":         ("STATE", "SIT"),
    "SUI/SDI - EMPLOYEE TAX":                 ("STATE", "SDI"),
    "SUI/SDI - EMPLOYER TAX":                 ("STATE", "ER_SUTA"),
    "FAMILY LEAVE INSURANCE - EMPLOYEE TAX":  ("STATE", "FLI"),
}


def lookup_canonical_tax(master_df, state_abbr, type_code):
    if master_df is None:
        return None
    pat = re.compile(rf"^\d{{2}}-000-0000-{re.escape(type_code)}-000$")
    sub = master_df[master_df["state_abbreviation"].astype(str).str.upper()
                    == state_abbr.upper()]
    if sub.empty:
        return None
    sub2 = sub[sub["unique_tax_id"].astype(str).apply(lambda s: bool(pat.match(s)))]
    if sub2.empty:
        broad = master_df[
            (master_df["state_abbreviation"].astype(str).str.upper() == state_abbr.upper())
            & master_df["unique_tax_id"].astype(str).str.contains(f"-{type_code}-", regex=False)
        ]
        if broad.empty:
            return None
        primary = broad[broad["sub_tax_desc"].fillna("").astype(str).str.strip() == ""]
        return primary.iloc[0] if not primary.empty else broad.iloc[0]
    primary = sub2[sub2["sub_tax_desc"].fillna("").astype(str).str.strip() == ""]
    return primary.iloc[0] if not primary.empty else sub2.iloc[0]


def build_tax_mapping(df, tax_cols, master_df):
    state_col = _find_col(df, ["WORKED IN STATE", "Worked In State", "State"])
    states = []
    if state_col:
        for v in df[state_col].dropna().astype(str):
            s = v.strip().upper()
            if s and s not in states and len(s) == 2:
                states.append(s)
    if not states:
        states = ["NY"]

    out_rows = []; not_found = []
    for tcol in tax_cols:
        key = str(tcol).strip().upper()
        scope_type = TAX_TOKEN_MAP.get(key)
        if not scope_type:
            not_found.append({"tax_column": str(tcol), "reason": "no rule defined"})
            continue
        scope, type_code = scope_type
        targets = ["FED"] if scope == "FED" else states
        for st_code in targets:
            rec = lookup_canonical_tax(master_df, st_code, type_code)
            if rec is None:
                not_found.append({"tax_column": str(tcol),
                                  "reason": f"{st_code} {type_code} not in master"})
                continue
            out_rows.append({
                "Source Tax Code": "",
                "Source Tax Code Name": str(tcol),
                "Source Tax Code Description": "",
                "Uzio Tax Code": rec.get("tax_code", ""),
                "Unique Tax ID": rec.get("unique_tax_id", ""),
                "Uzio Tax Code Description": rec.get("tax_name", ""),
                "Uzio Sub-Tax Description": rec.get("sub_tax_desc", "") or "",
            })
    return out_rows, states, not_found


def tax_mapping_to_csv_bytes(rows):
    cols = ["Source Tax Code", "Source Tax Code Name", "Source Tax Code Description",
            "Uzio Tax Code", "Unique Tax ID", "Uzio Tax Code Description",
            "Uzio Sub-Tax Description"]
    return pd.DataFrame(rows, columns=cols).to_csv(index=False).encode("utf-8")


# ---------- orchestrator ----------

def run_setup_helper(adp_file, master_csv_file):
    """Run the analysis. Returns (results_dict_of_lists, tax_csv_bytes, df)."""
    df, _, _ = read_input_file(adp_file)
    df = df.reset_index(drop=True)

    cats = categorize_columns(df)
    earn_rows = build_earnings_catalog(df, cats["earnings"], cats["hours"])

    total_earn_col = _find_col(df, ["TOTAL EARNINGS"]) or _find_col(df, ["GROSS PAY"])
    fit_taxable = _find_col(df, ["FEDERAL INCOME - EMPLOYEE TAXABLE"])
    fica_taxable = _find_col(df, ["SOCIAL SECURITY - EMPLOYEE TAXABLE"])
    medi_taxable = _find_col(df, ["MEDICARE - EMPLOYEE TAXABLE"])
    sit_taxable = _find_col(df, ["WORKED IN STATE - EMPLOYEE TAXABLE"])

    ded_rows = classify_deductions_pretax(
        df, cats["deductions"], total_earn_col,
        fit_taxable, fica_taxable, medi_taxable, sit_taxable,
    )
    contributions = [r for r in ded_rows if r.pop("_is_contribution", False)]
    deductions = [r for r in ded_rows if r not in contributions]
    for r in deductions:
        r.pop("_is_contribution", None)

    tax_rows = [{
        "Source Column": str(c).strip(),
        "Total $": round(float(df[c].apply(_num).sum()), 2),
        "Employees": int((df[c].apply(_num) != 0).sum()),
    } for c in cats["taxes"]]

    master_df = None
    if master_csv_file is not None:
        master_csv_file.seek(0)
        master_df = pd.read_csv(master_csv_file, dtype=str)
    tax_mapping_rows, states, missing = build_tax_mapping(df, cats["taxes"], master_df)

    bonus_info = classify_bonus(df, cats["earnings"])

    summary = [
        {"Metric": "Rows in file", "Value": len(df)},
        {"Metric": "Distinct earnings codes", "Value": len(earn_rows)},
        {"Metric": "Distinct contribution codes", "Value": len(contributions)},
        {"Metric": "Distinct deduction codes", "Value": len(deductions)},
        {"Metric": "Distinct tax columns", "Value": len(tax_rows)},
        {"Metric": "States detected", "Value": ", ".join(states) if states else "(none)"},
        {"Metric": "Tax mapping rows produced", "Value": len(tax_mapping_rows)},
        {"Metric": "Tax mapping rows missing from master", "Value": len(missing)},
        {"Metric": "Bonus classification verdict", "Value": bonus_info["verdict"]},
        {"Metric": "Bonus rows tested", "Value": bonus_info["rows_tested"]},
        {"Metric": "Bonus columns detected",
         "Value": ", ".join(bonus_info["bonus_columns_found"]) or "(none)"},
    ]

    bonus_rows = [{
        "Verdict": bonus_info["verdict"], "Reason": bonus_info["reason"],
        "Rows Tested": bonus_info["rows_tested"],
        "Discretionary Rows": bonus_info["discretionary_rows"],
        "Non-Discretionary Rows": bonus_info["non_discretionary_rows"],
        "Bonus Columns": ", ".join(bonus_info["bonus_columns_found"]),
    }]

    results = {
        "Summary": summary,
        "Earnings_Codes": earn_rows,
        "Contributions": contributions,
        "Deductions": deductions,
        "Taxes_Discovered": tax_rows,
        "Tax_Mapping": tax_mapping_rows,
        "Tax_Mapping_Missing": missing,
        "States_Detected": [{"State": s} for s in states],
        "Bonus_Classification": bonus_rows,
        "Bonus_Sample_Rows": bonus_info["samples"],
    }
    csv_bytes = tax_mapping_to_csv_bytes(tax_mapping_rows)
    return results, csv_bytes


def _results_to_xlsx_bytes(results):
    """Write the dict-of-lists to a multi-sheet xlsx in memory."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        for sheet_name, data in results.items():
            df = pd.DataFrame(data) if isinstance(data, list) else pd.DataFrame([data])
            if df.empty:
                df = pd.DataFrame([{"(no rows)": ""}])
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    return buf.getvalue()


# ---------- Streamlit UI ----------

def render_ui():
    st.title("ADP - Prior Payroll Setup Helper")
    st.markdown(
        """
Discovers what to configure in Uzio for an ADP Prior Payroll migration.

**What this tool produces:**

1. **Earnings_Codes** – every REGULAR / OVERTIME / `ADDITIONAL EARNINGS : XXX` code with `$` total, employee count, paired hours, and avg rate.
2. **Contributions** vs **Deductions** – voluntary deduction codes split by name pattern, each with **pre-tax vs post-tax** verdict and pre-tax flavor (`section_125` for medical/dental/vision; `401k_traditional` for retirement).
3. **Tax_Mapping** – a CSV in the exact `Payroll_Mappings_Tax_Mapping_CORRECTED` format. Federal taxes get one row each; state-scoped (SIT / SDI / SUTA / FLI) get **one row per distinct WORKED IN STATE** in the file.
4. **Bonus_Classification** – FLSA test: actual OT pay vs `1.5 × (REGULAR EARNINGS / REGULAR HOURS)`. Any single row showing the actual rate above the expected = bonus is non-discretionary for the whole file.

**Pre/post-tax algorithm:** for each row, `gap_FIT = TOTAL EARNINGS − FEDERAL INCOME - EMPLOYEE TAXABLE`. Try every subset of that row's non-zero deductions; if any subset sums to `gap_FIT` (within $0.02), every member is pre-tax for FIT. **One positive proof anywhere in the file = pre-tax for everyone.** Same logic on FICA / MEDI / SIT to derive the flavor.

**Tip:** Run **ADP - Prior Payroll Sanity Check** first if your file has interleaved totals rows or per-pay-period exports.
        """
    )

    col1, col2 = st.columns(2)
    with col1:
        adp_file = st.file_uploader(
            "ADP Prior Payroll File (sanitized)",
            type=["xlsx", "xls", "csv"],
            key="pps_helper_adp",
        )
    with col2:
        master_file = st.file_uploader(
            "State Tax Code Master CSV",
            type=["csv"],
            key="pps_helper_master",
            help="The Uzio State Tax Code master (state_abbreviation, tax_code, unique_tax_id, ...)",
        )

    if not adp_file:
        st.info("Upload an ADP Prior Payroll file to begin.")
        return
    if not master_file:
        st.warning("Upload the State Tax Code master CSV to populate Uzio Tax Codes in the Tax_Mapping sheet.")

    if not st.button("Run Setup Helper", type="primary"):
        return

    with st.spinner("Analyzing file..."):
        try:
            results, csv_bytes = run_setup_helper(adp_file, master_file)
        except Exception as e:
            st.error(f"Failed to run analysis: {e}")
            raise

    # --- Summary ---
    st.success("Analysis complete.")
    st.subheader("Summary")
    st.dataframe(pd.DataFrame(results["Summary"]), hide_index=True, use_container_width=True)

    # --- Bonus verdict (highlight) ---
    bonus = results["Bonus_Classification"][0]
    verdict = bonus["Verdict"]
    if verdict == "non_discretionary":
        st.error(f"**Bonus verdict: {verdict}** — {bonus['Reason']}")
    elif verdict == "discretionary":
        st.success(f"**Bonus verdict: {verdict}** — {bonus['Reason']}")
    else:
        st.warning(f"**Bonus verdict: {verdict}** — {bonus['Reason']}")
    if results["Bonus_Sample_Rows"]:
        with st.expander("Bonus test sample rows"):
            st.dataframe(pd.DataFrame(results["Bonus_Sample_Rows"]),
                         hide_index=True, use_container_width=True)

    # --- Catalogs ---
    st.subheader("Earnings Codes")
    st.dataframe(pd.DataFrame(results["Earnings_Codes"]),
                 hide_index=True, use_container_width=True)

    if results["Contributions"]:
        st.subheader("Contributions")
        st.dataframe(pd.DataFrame(results["Contributions"]),
                     hide_index=True, use_container_width=True)

    if results["Deductions"]:
        st.subheader("Deductions (with pre-tax / post-tax verdict)")
        st.dataframe(pd.DataFrame(results["Deductions"]),
                     hide_index=True, use_container_width=True)

    # --- Tax Mapping ---
    st.subheader("Tax Mapping")
    states = [s["State"] for s in results["States_Detected"]]
    st.caption(f"States detected: {', '.join(states) or '(none)'}")
    st.dataframe(pd.DataFrame(results["Tax_Mapping"]),
                 hide_index=True, use_container_width=True)
    if results["Tax_Mapping_Missing"]:
        with st.expander("Tax columns not resolved against master"):
            st.dataframe(pd.DataFrame(results["Tax_Mapping_Missing"]),
                         hide_index=True, use_container_width=True)

    # --- Downloads ---
    base = (adp_file.name or "ADP_Prior_Payroll").rsplit(".", 1)[0]
    st.subheader("Downloads")
    st.download_button(
        "Download Tax Mapping CSV",
        data=csv_bytes,
        file_name=f"{base}_Tax_Mapping.csv",
        mime="text/csv",
    )
    xlsx_bytes = _results_to_xlsx_bytes(results)
    st.download_button(
        "Download Full Setup Helper Report (xlsx)",
        data=xlsx_bytes,
        file_name=f"{base}_Setup_Helper.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
