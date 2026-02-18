import streamlit as st
import pandas as pd
import io
import re
import yaml
from datetime import date

# =========================================================
# Paycom to UZIO Federal/State Withholding Audit Tool (FIT/SIT)
# INPUT (uploads):
#   1) Paycom export (CSV) - wide
#   2) UZIO export (CSV) - long (employee_id, withholding_field_key, withholding_field_value)
#   3) Mapping.xlsx       - columns: Uzio Field Key, PayCom Column
# Optional:
#   4) key_mapping.yml            - UZIO key -> UI label (state/fed)
#   5) filing status_code.txt     - DB_KEY("UI Label")
#
# OUTPUT: Excel with 3 tabs (consistent with Unified Audit Tool)
#   1) Summary
#   2) Field_Summary_By_Status
#   3) Comparison_Detail_AllFields
# =========================================================

APP_TITLE = "Paycom to UZIO Withholding Audit Tool (FIT/SIT)"

ACTIVE_STATUSES = {"active", "on leave"}

STATUSES = [
    "Data Match",
    "Data Mismatch",
    "Value missing in Uzio (Paycom has value)",
    "Value missing in Paycom (Uzio has value)",
    "Employee ID Not Found in Uzio",
    "Employee ID Not Found in Paycom",
    "Column Missing in Paycom Sheet",
    "Column Missing in Uzio Sheet",
]

MISMATCH_STATUS_SET = {
    "Data Mismatch",
    "Value missing in Uzio (Paycom has value)",
    "Value missing in Paycom (Uzio has value)",
    "Employee ID Not Found in Uzio",
    "Employee ID Not Found in Paycom",
    "Column Missing in Paycom Sheet",
    "Column Missing in Uzio Sheet",
}

DETAIL_COLUMNS = [
    "Employee",
    "Field",                        # UZIO field key
    "Field Label",                  # from key_mapping.yml if available
    "Employment Status",            # Paycom status column
    "Paycom State",
    "Paycom Column",
    "UZIO_Value (raw)",
    "PAYCOM_Value (raw)",
    "Paycom Normalized",
    "UZIO Normalized / UI",
    "Rule Applied",
    "PAYCOM_SourceOfTruth_Status",  # one of STATUSES
]

NORMALIZATION_NOTES = [
    "Compare ONLY fields present in Mapping.xlsx.",
    "UZIO long format is pivoted wide by (employee_id, withholding_field_key) using first value per key.",
    "Filing Status: UZIO code → UI label via filing status_code file; compare case/punct-insensitive; allow substring match.",
    "Boolean: Yes/Y/1/True => True; No/N/0/False => False.",
    "Amounts: UZIO is cents, Paycom is dollars (UZIO/100), round to 2 decimals.",
    "Numeric blanks treated as 0; boolean blanks treated as unknown (both blank => match, else mismatch).",
]


# -------------------------
# Utilities
# -------------------------

def _norm_col(c):
    if c is None:
        return ""
    return str(c).strip().replace("\n", " ").strip()


def _pick_first(cols, candidates):
    lower_map = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


def _autodetect_paycom_cols(df):
    cols = list(df.columns)
    emp_id = _pick_first(cols, ["Employee_Code", "Employee ID", "Employee_ID", "Emp_ID", "employee_id"]) or cols[0]
    status = _pick_first(cols, ["Employee_Status", "Status", "Employee Status"]) or "Employee_Status"
    state = _pick_first(cols, ["State", "Work_State", "Home_State", "State_Abbreviation", "Paycom State"])
    first_name = _pick_first(cols, ["First_Name", "First Name", "Employee_First_Name", "FirstName"])
    last_name = _pick_first(cols, ["Last_Name", "Last Name", "Employee_Last_Name", "LastName"])
    return emp_id, status, state, first_name, last_name


def _read_mapping_xlsx(uploaded_mapping):
    df = pd.read_excel(uploaded_mapping, dtype=str)

    # Support a few variants, but default to strict keys.
    cols = {c.lower(): c for c in df.columns}

    uz_key_col = None
    pc_col_col = None

    # Most common
    if "uzio field key".lower() in cols:
        uz_key_col = cols["uzio field key".lower()]
    if "paycom column".lower() in cols:
        pc_col_col = cols["paycom column".lower()]

    # Variants
    if uz_key_col is None:
        uz_key_col = next((c for c in df.columns if "uzio" in c.lower() and "key" in c.lower()), None)
    if pc_col_col is None:
        pc_col_col = next((c for c in df.columns if "paycom" in c.lower() and "column" in c.lower()), None)

    if not uz_key_col or not pc_col_col:
        raise ValueError("Mapping.xlsx must include columns: 'Uzio Field Key' and 'PayCom Column'.")

    out = df[[uz_key_col, pc_col_col]].copy()
    out.columns = ["Uzio Field Key", "PayCom Column"]

    out["Uzio Field Key"] = out["Uzio Field Key"].astype(str).fillna("").str.strip()
    out["PayCom Column"] = out["PayCom Column"].astype(str).fillna("").str.strip()

    out = out[(out["Uzio Field Key"] != "") & (out["PayCom Column"] != "")]
    out = out.drop_duplicates(subset=["Uzio Field Key", "PayCom Column"], keep="first").reset_index(drop=True)
    return out


def _pivot_uzio_long_to_wide(df_long):
    required = {
        "employee_id",
        "employee_first_name",
        "employee_last_name",
        "withholding_field_key",
        "withholding_field_value",
    }
    missing = required - set(df_long.columns)
    if missing:
        raise ValueError(f"UZIO CSV missing required columns: {sorted(missing)}")

    uz = df_long.copy()
    for c in required:
        uz[c] = uz[c].astype(str).fillna("")

    wide = (
        uz.pivot_table(
            index="employee_id",
            columns="withholding_field_key",
            values="withholding_field_value",
            aggfunc="first",
        )
        .reset_index()
    )

    names = uz.groupby("employee_id")[["employee_first_name", "employee_last_name"]].first().reset_index()
    wide = wide.merge(names, on="employee_id", how="left")
    wide.columns = [str(c) for c in wide.columns]
    return wide


def _load_key_mapping_yml_bytes(yml_bytes):
    if not yml_bytes:
        return {}
    raw = yaml.safe_load(yml_bytes)

    labels_by_state = {}
    try:
        mappings = raw["withholding_es"]["mappings"]
    except Exception:
        mappings = raw

    if isinstance(mappings, dict):
        for state, state_map in mappings.items():
            if not isinstance(state_map, dict):
                continue
            labels_by_state[state] = {}
            for k, v in state_map.items():
                if isinstance(v, dict) and "label" in v:
                    labels_by_state[state][k] = str(v["label"])
                elif isinstance(v, str):
                    labels_by_state[state][k] = v
    return labels_by_state


def _load_filing_status_code_bytes(txt_bytes):
    if not txt_bytes:
        return {}
    text = txt_bytes.decode("utf-8", errors="ignore")
    pattern = re.compile(r'([A-Z0-9_]+)\("([^"]+)"\)')
    out = {}
    for code, label in pattern.findall(text):
        out[code.strip()] = label.strip()
    return out


def _norm_text(s):
    s = "" if s is None else str(s)
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9\s]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_bool(raw):
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if s == "":
        return None
    if s in {"yes", "y", "true", "1", "t"}:
        return True
    if s in {"no", "n", "false", "0", "f"}:
        return False
    return None


def _parse_number(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    if s == "":
        return None
    s = s.replace(",", "").replace("$", "")
    try:
        return float(s)
    except Exception:
        return None


def _infer_type(uzio_key, paycom_col):
    k = (uzio_key or "").upper()
    pc = (paycom_col or "").lower()

    if k in {"FIT_FILING_STATUS", "SIT_FILING_STATUS"}:
        return "filing_status"

    # Heuristic amount keys (also handles paycom columns that look like money)
    if ("$" in pc) or any(x in k for x in ["OTHER_INCOME", "ADDL", "WITHHOLDING", "CREDIT", "DEDUCTION", "OVERRIDE"]):
        return "amount"

    # Heuristic boolean keys
    if any(x in k for x in ["EXEMPT", "FLAG", "HIGHER", "NON_RESIDENT", "RESIDENT", "CERTIFICATE", "MULTIPLE_JOBS"]):
        return "boolean"

    # Heuristic integer keys
    if any(x in k for x in ["ALLOWANCE", "EXEMPTION", "NUMBER", "TOTAL", "COUNT"]):
        return "integer"

    return "string"


def _field_label_for(uzio_key, state, labels_by_state):
    key = (uzio_key or "").strip()
    st_code = (state or "").strip().upper()

    if st_code and st_code in labels_by_state and key in labels_by_state[st_code]:
        return labels_by_state[st_code][key]
    if "FED" in labels_by_state and key in labels_by_state["FED"]:
        return labels_by_state["FED"][key]

    for mp in labels_by_state.values():
        if key in mp:
            return mp[key]

    return key.replace("_", " ").title()


def _compare_filing_status(pay_raw, uz_code, filing_map):
    pc = "" if pay_raw is None else str(pay_raw).strip()
    uz = "" if uz_code is None else str(uz_code).strip()

    if pc == "" and uz == "":
        return True, "", "", "Filing status: both blank"

    if uz == "":
        # Treat as missing in Uzio
        return False, pc, "", "Filing status missing in Uzio"

    ui = filing_map.get(uz)
    if ui is None:
        return False, pc, "", "Filing status code not found in mapping file"

    pc_n = _norm_text(pc)
    ui_n = _norm_text(ui)

    if pc_n == ui_n or (pc_n and pc_n in ui_n) or (ui_n and ui_n in pc_n):
        return True, pc, ui, "Filing status match (substring/punct-insensitive)"

    return False, pc, ui, "Filing status mismatch after UI mapping"


def _compare_amount(pay_raw, uz_raw):
    pc = _parse_number(pay_raw)
    uz = _parse_number(uz_raw)

    pc = 0.0 if pc is None else pc
    uz = 0.0 if uz is None else uz

    uz_dollars = round(uz / 100.0, 2)
    pc_dollars = round(pc, 2)

    return (pc_dollars == uz_dollars), pc_dollars, uz_dollars, "Amount: UZIO cents→dollars (/100)"


def _compare_integer(pay_raw, uz_raw):
    pc = _parse_number(pay_raw)
    uz = _parse_number(uz_raw)
    pc_i = int(pc) if pc is not None else 0
    uz_i = int(uz) if uz is not None else 0
    return (pc_i == uz_i), pc_i, uz_i, "Integer: blank→0"


def _compare_boolean(pay_raw, uz_raw):
    pc_b = _parse_bool(pay_raw)
    uz_b = _parse_bool(uz_raw)

    if pc_b is None and uz_b is None:
        return True, None, None, "Boolean: both blank"
    if pc_b is None or uz_b is None:
        return False, pc_b, uz_b, "Boolean: blank vs value"
    return (pc_b == uz_b), pc_b, uz_b, "Boolean: Yes/No ↔ True/False"


def _compare_string(pay_raw, uz_raw):
    pc = "" if pay_raw is None else str(pay_raw).strip()
    uz = "" if uz_raw is None else str(uz_raw).strip()
    if pc == "" and uz == "":
        return True, "", "", "String: both blank"
    return (_norm_text(pc) == _norm_text(uz)), pc, uz, "String: case/punct-insensitive"


# -------------------------
# Core audit (build comparison detail + summaries)
# -------------------------

def run_withholding_audit(paycom_df, uzio_long_df, mapping_df, labels_by_state, filing_map,
                         paycom_emp_id_col, paycom_status_col, paycom_state_col, paycom_fn_col, paycom_ln_col):

    uzio_wide = _pivot_uzio_long_to_wide(uzio_long_df)

    # Normalize IDs
    pay = paycom_df.copy()
    pay[paycom_emp_id_col] = pay[paycom_emp_id_col].astype(str).fillna("").str.strip()
    uzio_wide["employee_id"] = uzio_wide["employee_id"].astype(str).fillna("").str.strip()

    # Ensure Paycom status col exists
    if paycom_status_col not in pay.columns:
        pay[paycom_status_col] = ""

    # Sets
    pay_ids = set(pay[paycom_emp_id_col].replace("", pd.NA).dropna().tolist())
    uz_ids = set(uzio_wide["employee_id"].replace("", pd.NA).dropna().tolist())
    all_ids = sorted(list(pay_ids | uz_ids))

    # Index lookups
    pay_idx = {str(x): i for i, x in enumerate(pay[paycom_emp_id_col].astype(str))}
    uz_idx = {str(x): i for i, x in enumerate(uzio_wide["employee_id"].astype(str))}

    rows = []

    for eid in all_ids:
        p_i = pay_idx.get(eid)
        u_i = uz_idx.get(eid)

        p_missing_row = p_i is None
        u_missing_row = u_i is None

        # context
        p_status = ""
        p_state = ""
        if not p_missing_row:
            p_status = str(pay.loc[p_i, paycom_status_col]) if paycom_status_col in pay.columns else ""
            if paycom_state_col and paycom_state_col in pay.columns:
                p_state = str(pay.loc[p_i, paycom_state_col])

        for _, mr in mapping_df.iterrows():
            uz_key = mr["Uzio Field Key"]
            pc_col = mr["PayCom Column"]

            u_missing_col = (uz_key not in uzio_wide.columns)
            p_missing_col = (pc_col not in pay.columns)

            uz_val = ""
            pc_val = ""
            if (not u_missing_row) and (not u_missing_col):
                uz_val = uzio_wide.loc[u_i, uz_key]
            if (not p_missing_row) and (not p_missing_col):
                pc_val = pay.loc[p_i, pc_col]

            # Determine status
            if p_missing_row and (not u_missing_row):
                status = "Employee ID Not Found in Paycom"
            elif u_missing_row and (not p_missing_row):
                status = "Employee ID Not Found in Uzio"
            elif p_missing_col:
                status = "Column Missing in Paycom Sheet"
            elif u_missing_col:
                status = "Column Missing in Uzio Sheet"
            else:
                dtype = _infer_type(uz_key, pc_col)
                if dtype == "filing_status":
                    same, pnorm, unorm, rule = _compare_filing_status(pc_val, uz_val, filing_map)
                    # If UZIO has blank but Paycom has value, treat as "Value missing in Uzio"
                    if not same and rule == "Filing status missing in Uzio":
                        status = "Value missing in Uzio (Paycom has value)" if _norm_text(pc_val) != "" else "Data Mismatch"
                    elif not same and rule == "Filing status code not found in mapping file":
                        status = "Data Mismatch"
                    else:
                        status = "Data Match" if same else "Data Mismatch"
                elif dtype == "amount":
                    same, pnorm, unorm, rule = _compare_amount(pc_val, uz_val)
                    if same:
                        status = "Data Match"
                    else:
                        uz_b = _norm_text(uz_val)
                        pc_b = _norm_text(pc_val)
                        if uz_b == "" and pc_b != "":
                            status = "Value missing in Uzio (Paycom has value)"
                        elif uz_b != "" and pc_b == "":
                            status = "Value missing in Paycom (Uzio has value)"
                        else:
                            status = "Data Mismatch"
                elif dtype == "integer":
                    same, pnorm, unorm, rule = _compare_integer(pc_val, uz_val)
                    if same:
                        status = "Data Match"
                    else:
                        uz_b = _norm_text(uz_val)
                        pc_b = _norm_text(pc_val)
                        if uz_b == "" and pc_b != "":
                            status = "Value missing in Uzio (Paycom has value)"
                        elif uz_b != "" and pc_b == "":
                            status = "Value missing in Paycom (Uzio has value)"
                        else:
                            status = "Data Mismatch"
                elif dtype == "boolean":
                    same, pnorm, unorm, rule = _compare_boolean(pc_val, uz_val)
                    if same:
                        status = "Data Match"
                    else:
                        # boolean blank special: "blank vs value" should count as missing on the blank side
                        uz_b = _norm_text(uz_val)
                        pc_b = _norm_text(pc_val)
                        if uz_b == "" and pc_b != "":
                            status = "Value missing in Uzio (Paycom has value)"
                        elif uz_b != "" and pc_b == "":
                            status = "Value missing in Paycom (Uzio has value)"
                        else:
                            status = "Data Mismatch"
                else:
                    same, pnorm, unorm, rule = _compare_string(pc_val, uz_val)
                    if same:
                        status = "Data Match"
                    else:
                        uz_b = _norm_text(uz_val)
                        pc_b = _norm_text(pc_val)
                        if uz_b == "" and pc_b != "":
                            status = "Value missing in Uzio (Paycom has value)"
                        elif uz_b != "" and pc_b == "":
                            status = "Value missing in Paycom (Uzio has value)"
                        else:
                            status = "Data Mismatch"

                # dtype compare returns pnorm/unorm/rule; if we are here ensure they exist
                if dtype != "filing_status" and dtype != "amount" and dtype != "integer" and dtype != "boolean" and dtype != "string":
                    pass
            # For missing/column errors, set normalized fields to blanks
            if status in {
                "Employee ID Not Found in Paycom",
                "Employee ID Not Found in Uzio",
                "Column Missing in Paycom Sheet",
                "Column Missing in Uzio Sheet",
            }:
                pnorm, unorm, rule = "", "", ""

            label = _field_label_for(uz_key, p_state, labels_by_state)

            rows.append({
                "Employee": eid,
                "Field": uz_key,
                "Field Label": label,
                "Employment Status": p_status,
                "Paycom State": p_state,
                "Paycom Column": pc_col,
                "UZIO_Value (raw)": uz_val,
                "PAYCOM_Value (raw)": pc_val,
                "Paycom Normalized": pnorm,
                "UZIO Normalized / UI": unorm,
                "Rule Applied": rule,
                "PAYCOM_SourceOfTruth_Status": status,
            })

    comparison_detail = pd.DataFrame(rows, columns=DETAIL_COLUMNS)

    # Field summary
    if not comparison_detail.empty:
        field_summary_by_status = (
            comparison_detail.pivot_table(
                index="Field",
                columns="PAYCOM_SourceOfTruth_Status",
                values="Employee",
                aggfunc="count",
                fill_value=0,
            )
            .reindex(columns=STATUSES, fill_value=0)
            .reset_index()
        )
        field_summary_by_status["Total"] = field_summary_by_status[STATUSES].sum(axis=1)
    else:
        field_summary_by_status = pd.DataFrame(columns=["Field"] + STATUSES + ["Total"])

    # Summary metrics
    # Active mismatch count (row-level)
    if not comparison_detail.empty:
        active_mask = comparison_detail["Employment Status"].astype(str).str.strip().str.lower().isin(ACTIVE_STATUSES)
        mismatch_mask = comparison_detail["PAYCOM_SourceOfTruth_Status"].isin(MISMATCH_STATUS_SET)
        active_mismatch_rows = int((active_mask & mismatch_mask).sum())
        total_mismatch_rows = int(mismatch_mask.sum())
    else:
        active_mismatch_rows = 0
        total_mismatch_rows = 0

    summary = pd.DataFrame(
        {
            "Metric": [
                "Total UZIO Employees",
                "Total PAYCOM Employees",
                "Employees in both",
                "Employees only in UZIO",
                "Employees only in PAYCOM",
                "Fields Compared",
                "Total Comparisons (field-level rows)",
                "Total mismatches (mapped only)",
                "Active mismatches (mapped only)",
            ],
            "Value": [
                len(uz_ids),
                len(pay_ids),
                len(uz_ids & pay_ids),
                len(uz_ids - pay_ids),
                len(pay_ids - uz_ids),
                int(mapping_df.shape[0]),
                int(comparison_detail.shape[0]),
                total_mismatch_rows,
                active_mismatch_rows,
            ],
        }
    )

    # Missing in UZIO (employee-level list) as a second block in Summary sheet
    missing_in_uzio = pay[~pay[paycom_emp_id_col].isin(list(uz_ids))].copy()
    missing_list = pd.DataFrame({
        "Employee ID": missing_in_uzio[paycom_emp_id_col].astype(str) if paycom_emp_id_col in missing_in_uzio.columns else "",
        "Employee Status": missing_in_uzio[paycom_status_col].astype(str) if paycom_status_col in missing_in_uzio.columns else "",
        "First Name": missing_in_uzio[paycom_fn_col].astype(str) if paycom_fn_col and paycom_fn_col in missing_in_uzio.columns else "",
        "Last Name": missing_in_uzio[paycom_ln_col].astype(str) if paycom_ln_col and paycom_ln_col in missing_in_uzio.columns else "",
        "State": missing_in_uzio[paycom_state_col].astype(str) if paycom_state_col and paycom_state_col in missing_in_uzio.columns else "",
    })

    return summary, field_summary_by_status, comparison_detail, missing_list


def build_report_bytes(summary, field_summary_by_status, comparison_detail, missing_list):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        # Write Summary metrics
        summary.to_excel(writer, sheet_name="Summary", index=False, startrow=0)

        # Write missing employee list + normalization notes on the same Summary sheet
        ws = writer.book["Summary"]
        start_row = len(summary) + 3
        ws.cell(row=start_row, column=1, value="Missing in UZIO (Paycom-only)")
        ws.cell(row=start_row, column=1).font = ws.cell(row=1, column=1).font.copy(bold=True)

        missing_list.to_excel(writer, sheet_name="Summary", index=False, startrow=start_row, startcol=0)

        notes_row = start_row + len(missing_list) + 3
        ws.cell(row=notes_row, column=1, value="Normalization Rules Applied")
        ws.cell(row=notes_row, column=1).font = ws.cell(row=1, column=1).font.copy(bold=True)
        for i, line in enumerate(NORMALIZATION_NOTES, start=notes_row + 1):
            ws.cell(row=i, column=1, value=f"• {line}")

        # Other sheets
        field_summary_by_status.to_excel(writer, sheet_name="Field_Summary_By_Status", index=False)
        comparison_detail.to_excel(writer, sheet_name="Comparison_Detail_AllFields", index=False)

    return out.getvalue()


# -------------------------
# UI
# -------------------------

def render_ui():
    st.title(APP_TITLE)
    st.write(
        "Upload Paycom CSV (wide), UZIO CSV (long key-value), and Mapping.xlsx. "
        "Optional: key_mapping.yml + filing status_code file for labels + filing status UI mapping."
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        paycom_file = st.file_uploader("Paycom export (CSV)", type=["csv"])
    with c2:
        uzio_file = st.file_uploader("UZIO export (CSV - long format)", type=["csv"])
    with c3:
        mapping_file = st.file_uploader("Mapping.xlsx", type=["xlsx"])

    with st.expander("Optional reference files"):
        yml_file = st.file_uploader("key_mapping.yml (optional)", type=["yml", "yaml"])
        filing_file = st.file_uploader("filing status_code.txt (optional)", type=["txt", "csv"])

    run_btn = st.button("Run Audit", type="primary", disabled=not (paycom_file and uzio_file and mapping_file))

    if run_btn:
        try:
            with st.spinner("Running audit..."):
                paycom_df = pd.read_csv(paycom_file, dtype=str, keep_default_na=False)
                uzio_long_df = pd.read_csv(uzio_file, dtype=str, keep_default_na=False)
                mapping_df = _read_mapping_xlsx(mapping_file)

                # Load optional mappings
                labels_by_state = {}
                filing_map = {}

                if yml_file:
                    labels_by_state = _load_key_mapping_yml_bytes(yml_file.getvalue())
                else:
                    # Try local file if bundled in repo
                    try:
                        with open("key_mapping.yml", "rb") as f:
                            labels_by_state = _load_key_mapping_yml_bytes(f.read())
                    except Exception:
                        labels_by_state = {}

                if filing_file:
                    filing_map = _load_filing_status_code_bytes(filing_file.getvalue())
                else:
                    try:
                        with open("filing status_code.txt", "rb") as f:
                            filing_map = _load_filing_status_code_bytes(f.read())
                    except Exception:
                        filing_map = {}

                emp_id_col, status_col, state_col, fn_col, ln_col = _autodetect_paycom_cols(paycom_df)

                with st.expander("Advanced: override Paycom key columns"):
                    cols = list(paycom_df.columns)
                    emp_id_col = st.selectbox("Employee ID column", cols, index=cols.index(emp_id_col) if emp_id_col in cols else 0)
                    status_col = st.selectbox("Employee Status column", cols, index=cols.index(status_col) if status_col in cols else 0)

                    state_col = st.selectbox("State column (optional)", ["(none)"] + cols, index=0 if not state_col else (["(none)"] + cols).index(state_col))
                    fn_col = st.selectbox("First Name column (optional)", ["(none)"] + cols, index=0 if not fn_col else (["(none)"] + cols).index(fn_col))
                    ln_col = st.selectbox("Last Name column (optional)", ["(none)"] + cols, index=0 if not ln_col else (["(none)"] + cols).index(ln_col))

                    if state_col == "(none)":
                        state_col = None
                    if fn_col == "(none)":
                        fn_col = None
                    if ln_col == "(none)":
                        ln_col = None

                summary, field_summary, detail, missing_list = run_withholding_audit(
                    paycom_df=paycom_df,
                    uzio_long_df=uzio_long_df,
                    mapping_df=mapping_df,
                    labels_by_state=labels_by_state,
                    filing_map=filing_map,
                    paycom_emp_id_col=emp_id_col,
                    paycom_status_col=status_col,
                    paycom_state_col=state_col,
                    paycom_fn_col=fn_col,
                    paycom_ln_col=ln_col,
                )

                report_bytes = build_report_bytes(summary, field_summary, detail, missing_list)

            st.success("Report generated.")
            today_str = date.today().isoformat()
            out_filename = f"Client_Name_Paycom_UZIO_Withholding_Audit_{today_str}.xlsx"

            st.download_button(
                label="Download Audit Report",
                data=report_bytes,
                file_name=out_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            st.subheader("Summary (preview)")
            st.dataframe(summary, use_container_width=True)

            st.subheader("Field Summary (preview)")
            st.dataframe(field_summary.head(50), use_container_width=True)

            st.subheader("Comparison Detail (preview)")
            st.dataframe(detail.head(50), use_container_width=True)

        except Exception as e:
            st.error(f"An unexpected error occurred: {e}")
            st.exception(e)
