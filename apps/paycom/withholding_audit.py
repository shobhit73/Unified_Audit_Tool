import streamlit as st
import pandas as pd
import io
import re
import yaml
from datetime import date

# =========================================================
# Paycom to UZIO Federal/State Withholding Audit Tool (FIT/SIT)
# =========================================================

APP_TITLE = "Paycom to UZIO Withholding Audit Tool (FIT/SIT)"

ACTIVE_STATUSES = {"active", "on leave"}

DETAIL_COLUMNS = [
    "Employee ID",
    "Paycom Status",
    "Paycom State",
    "Paycom First Name",
    "Paycom Last Name",
    "UZIO First Name",
    "UZIO Last Name",
    "Field Label",
    "Paycom Column",
    "Paycom Value",
    "UZIO Field Key",
    "UZIO Stored Value",
    "Paycom Normalized",
    "UZIO Normalized / UI",
    "Rule Applied"
]

NORMALIZATION_NOTES = [
    "1. Filing Status stored in UZIO as DB value (e.g. FEDERAL_SINGLE) is mapped to UI label (e.g. Single). Match is substring and punct-insensitive.",
    "2. Boolean: Yes/Y/1/True => True; No/N/0/False => False.",
    "3. Amounts: UZIO stores in cents (divided by 100). Paycom stores in dollars.",
    "4. Blank handling: Numerics blank=0, Booleans blank=unknown.",
    "5. Fields compared strictly to what is available in Mapping file.",
]

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
    emp_id = _pick_first(cols, ["Employee_Code", "Employee Code", "Employee ID", "Employee_ID", "Emp_ID", "employee_id", "EE Code"]) or cols[0]
    status = _pick_first(cols, ["Employee_Status", "Status", "Employee Status"]) or cols[0]
    state = _pick_first(cols, ["State", "Work_State", "Home_State", "State_Abbreviation", "Paycom State"])
    first_name = _pick_first(cols, ["First_Name", "First Name", "Employee_First_Name", "FirstName", "EE Name"])
    last_name = _pick_first(cols, ["Last_Name", "Last Name", "Employee_Last_Name", "LastName"])
    return emp_id, status, state, first_name, last_name

def _read_mapping_xlsx(uploaded_mapping):
    df = pd.read_excel(uploaded_mapping, dtype=str)
    cols = {c.lower(): c for c in df.columns}
    
    uz_key_col = _pick_first(df.columns, ["Uzio Field Key", "Uzio_Field_Key", "Uzio Key", "UZIO Field"])
    pc_col_col = _pick_first(df.columns, ["PayCom Column", "Paycom_Column", "Paycom Column", "Source Column"])

    if not uz_key_col or not pc_col_col:
        raise ValueError("Mapping.xlsx must include columns resembling 'Uzio Field Key' and 'PayCom Column'.")

    out = df[[uz_key_col, pc_col_col]].copy()
    
    # Store logic and type dynamically for Tab 5 if found
    logic_col = _pick_first(df.columns, ["Comments", "Comment", "Logic", "Notes"])
    
    out.columns = ["Uzio Field Key", "PayCom Column"]
    out["Uzio Field Key"] = out["Uzio Field Key"].astype(str).fillna("").apply(lambda x: x.strip())
    out["PayCom Column"] = out["PayCom Column"].astype(str).fillna("").apply(lambda x: x.strip())
    if logic_col:
        out["Comments"] = df[logic_col].astype(str).fillna("").apply(lambda x: x.strip() if x.lower() != 'nan' else "")
    else:
        out["Comments"] = ""

    out = out[(out["Uzio Field Key"] != "") & (out["PayCom Column"] != "")]
    out = out.drop_duplicates(subset=["Uzio Field Key", "PayCom Column"], keep="first").reset_index(drop=True)
    return out

def _pivot_uzio_long_to_wide(df_long):
    required = {"employee_id", "withholding_field_key", "withholding_field_value"}
    missing = required - set(df_long.columns)
    if missing:
        raise ValueError(f"UZIO CSV missing required columns: {sorted(missing)}")

    uz = df_long.copy()
    for c in required:
        uz[c] = uz[c].astype(str).fillna("")

    wide = uz.pivot_table(index="employee_id", columns="withholding_field_key", values="withholding_field_value", aggfunc="first").reset_index()

    # Get names
    has_fn = "employee_first_name" in uz.columns
    has_ln = "employee_last_name" in uz.columns
    cols_to_get = []
    if has_fn: cols_to_get.append("employee_first_name")
    if has_ln: cols_to_get.append("employee_last_name")
    
    if cols_to_get:
        names = uz.groupby("employee_id")[cols_to_get].first().reset_index()
        wide = wide.merge(names, on="employee_id", how="left")
    
    wide.columns = [str(c) for c in wide.columns]
    return wide

def _load_key_mapping_yml_bytes(yml_bytes):
    if not yml_bytes: return {}
    try:
        raw = yaml.safe_load(yml_bytes)
        labels_by_state = {}
        mappings = raw.get("withholding_es", {}).get("mappings", raw)
        if isinstance(mappings, dict):
            for state, state_map in mappings.items():
                if not isinstance(state_map, dict): continue
                labels_by_state[state] = {}
                for k, v in state_map.items():
                    if isinstance(v, dict) and "label" in v:
                        labels_by_state[state][k] = str(v["label"])
                    elif isinstance(v, str):
                        labels_by_state[state][k] = v
        return labels_by_state
    except:
        return {}

def _load_filing_status_code_bytes(txt_bytes):
    if not txt_bytes: return {}
    text = txt_bytes.decode("utf-8", errors="ignore")
    pattern = re.compile(r'([A-Z0-9_]+)\("([^"]+)"\)')
    out = {}
    for code, label in pattern.findall(text):
        out[code.strip()] = label.strip()
    return out

def _norm_text(s):
    s = "" if pd.isna(s) else str(s)
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9\s]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _parse_bool(raw):
    if pd.isna(raw): return None
    s = str(raw).strip().lower()
    if s == "" or s == "nan": return None
    if s in {"yes", "y", "true", "1", "t", "on"}: return True
    if s in {"no", "n", "false", "0", "f", "off"}: return False
    return None

def _parse_number(raw):
    if pd.isna(raw): return 0.0
    s = str(raw).strip()
    if s == "" or s.lower() == "nan": return 0.0
    s = s.replace(",", "").replace("$", "")
    try:
        if s.startswith("(") and s.endswith(")"):
            return -float(s[1:-1])
        return float(s)
    except:
        return 0.0

def _infer_type(uzio_key, paycom_col):
    k = (uzio_key or "").upper()
    pc = (paycom_col or "").lower()
    if k in {"FIT_FILING_STATUS", "SIT_FILING_STATUS"}: return "filing_status"
    if ("$" in pc) or any(x in k for x in ["OTHER_INCOME", "ADDL", "WITHHOLDING", "CREDIT", "DEDUCTION", "OVERRIDE"]): return "amount"
    if any(x in k for x in ["EXEMPT", "FLAG", "HIGHER", "NON_RESIDENT", "RESIDENT", "CERTIFICATE", "MULTIPLE_JOBS"]): return "boolean"
    if any(x in k for x in ["ALLOWANCE", "EXEMPTION", "NUMBER", "TOTAL", "COUNT"]): return "integer"
    return "string"

def _field_label_for(uzio_key, state, labels_by_state):
    key = (uzio_key or "").strip()
    st_code = (state or "").strip().upper()
    if st_code and st_code in labels_by_state and key in labels_by_state[st_code]: return labels_by_state[st_code][key]
    if "FED" in labels_by_state and key in labels_by_state["FED"]: return labels_by_state["FED"][key]
    for mp in labels_by_state.values():
        if key in mp: return mp[key]
    return key.replace("_", " ").title()

# --- Comparisons ---
def _compare_filing_status(pay_raw, uz_code, filing_map):
    pc = "" if pd.isna(pay_raw) else str(pay_raw).strip()
    uz = "" if pd.isna(uz_code) else str(uz_code).strip()
    if pc == "" and uz == "": return True, "", "", "Both blank"
    if uz == "": return False, pc, "", "Value missing in UZIO"
    ui = filing_map.get(uz)
    if ui is None: return False, pc, "", "Filing status code not found in mapping file"
    pc_n = _norm_text(pc)
    ui_n = _norm_text(ui)
    if pc_n == ui_n or (pc_n and pc_n in ui_n) or (ui_n and ui_n in pc_n): return True, pc, ui, "Matched normalized UI string"
    return False, pc, ui, "Filing Status mismatch"

def _compare_amount(pay_raw, uz_raw):
    pc = _parse_number(pay_raw)
    uz = _parse_number(uz_raw)
    uz_dollars = round(uz / 100.0, 2) if uz_raw else 0.0
    pc_dollars = round(pc, 2)
    return (abs(pc_dollars - uz_dollars) < 0.01), str(pc_dollars), str(uz_dollars), "Divide UZIO by 100 (Cents), blank=0"

def _compare_integer(pay_raw, uz_raw):
    pc_i = int(_parse_number(pay_raw))
    uz_i = int(_parse_number(uz_raw))
    return (pc_i == uz_i), str(pc_i), str(uz_i), "Integer match, blank=0"

def _compare_boolean(pay_raw, uz_raw):
    pc_b = _parse_bool(pay_raw)
    uz_b = _parse_bool(uz_raw)
    if pc_b is None and uz_b is None: return True, "", "", "Both blank"
    if pc_b is None or uz_b is None: return False, str(pc_b), str(uz_b), "Blank vs Value"
    return (pc_b == uz_b), str(pc_b), str(uz_b), "Boolean match"

def _compare_string(pay_raw, uz_raw):
    pc = "" if pd.isna(pay_raw) else str(pay_raw).strip()
    uz = "" if pd.isna(uz_raw) else str(uz_raw).strip()
    if pc == "" and uz == "": return True, "", "", "Both blank"
    return (_norm_text(pc) == _norm_text(uz)), pc, uz, "String match"


def run_withholding_audit(paycom_df, uzio_long_df, mapping_df, labels_by_state, filing_map,
                         paycom_emp_id_col, paycom_status_col, paycom_state_col, paycom_fn_col, paycom_ln_col):

    uzio_wide = _pivot_uzio_long_to_wide(uzio_long_df)

    # Normalize IDs
    pay = paycom_df.copy()
    pay[paycom_emp_id_col] = pay[paycom_emp_id_col].astype(str).fillna("").str.strip()
    uzio_wide["employee_id"] = uzio_wide["employee_id"].astype(str).fillna("").str.strip()

    pay_ids = set(pay[paycom_emp_id_col].replace("nan", "").replace("", pd.NA).dropna().tolist())
    uz_ids = set(uzio_wide["employee_id"].replace("nan", "").replace("", pd.NA).dropna().tolist())
    all_ids = sorted(list(pay_ids | uz_ids))

    pay_idx = {str(x): i for i, x in enumerate(pay[paycom_emp_id_col].astype(str))}
    uz_idx = {str(x): i for i, x in enumerate(uzio_wide["employee_id"].astype(str))}

    mismatches = []
    
    # Tracking fields actually used for mappings tab
    fields_used = []

    for eid in all_ids:
        p_i = pay_idx.get(eid)
        u_i = uz_idx.get(eid)

        p_missing_row = p_i is None
        u_missing_row = u_i is None

        p_status = str(pay.loc[p_i, paycom_status_col]) if not p_missing_row and paycom_status_col in pay.columns else ""
        p_state = str(pay.loc[p_i, paycom_state_col]) if not p_missing_row and paycom_state_col and paycom_state_col in pay.columns else ""
        p_first = str(pay.loc[p_i, paycom_fn_col]) if not p_missing_row and paycom_fn_col and paycom_fn_col in pay.columns else ""
        p_last = str(pay.loc[p_i, paycom_ln_col]) if not p_missing_row and paycom_ln_col and paycom_ln_col in pay.columns else ""
        
        u_first = str(uzio_wide.loc[u_i, "employee_first_name"]) if not u_missing_row and "employee_first_name" in uzio_wide.columns else ""
        u_last = str(uzio_wide.loc[u_i, "employee_last_name"]) if not u_missing_row and "employee_last_name" in uzio_wide.columns else ""

        for _, mr in mapping_df.iterrows():
            uz_key = mr["Uzio Field Key"]
            pc_col = mr["PayCom Column"]

            u_missing_col = (uz_key not in uzio_wide.columns)
            p_missing_col = (pc_col not in pay.columns)

            uz_val = uzio_wide.loc[u_i, uz_key] if not u_missing_row and not u_missing_col else ""
            pc_val = pay.loc[p_i, pc_col] if not p_missing_row and not p_missing_col else ""

            dtype = _infer_type(uz_key, pc_col)
            label = _field_label_for(uz_key, p_state, labels_by_state)
            
            if eid == all_ids[0]: # Store mapping info once
                fields_used.append({
                    "Uzio Field Key": uz_key,
                    "Field Label": label,
                    "Paycom Column": pc_col,
                    "Data Type": dtype,
                    "Logic": mr["Comments"]
                })

            if p_missing_row or u_missing_row or p_missing_col or u_missing_col:
                continue # Skip pure missing ID/Col row noise for mismatches list

            is_match = False
            if dtype == "filing_status":
                is_match, pn, un, r = _compare_filing_status(pc_val, uz_val, filing_map)
            elif dtype == "amount":
                is_match, pn, un, r = _compare_amount(pc_val, uz_val)
            elif dtype == "integer":
                is_match, pn, un, r = _compare_integer(pc_val, uz_val)
            elif dtype == "boolean":
                is_match, pn, un, r = _compare_boolean(pc_val, uz_val)
            else:
                is_match, pn, un, r = _compare_string(pc_val, uz_val)

            if not is_match:
                mismatches.append({
                    "Employee ID": eid,
                    "Paycom Status": p_status,
                    "Paycom State": p_state,
                    "Paycom First Name": p_first,
                    "Paycom Last Name": p_last,
                    "UZIO First Name": u_first,
                    "UZIO Last Name": u_last,
                    "Field Label": label,
                    "Paycom Column": pc_col,
                    "Paycom Value": str(pc_val),
                    "UZIO Field Key": uz_key,
                    "UZIO Stored Value": str(uz_val),
                    "Paycom Normalized": pn,
                    "UZIO Normalized / UI": un,
                    "Rule Applied": r
                })

    all_miss_df = pd.DataFrame(mismatches, columns=DETAIL_COLUMNS)
    
    act_miss_df = pd.DataFrame(columns=DETAIL_COLUMNS)
    if not all_miss_df.empty:
        act_miss_df = all_miss_df[all_miss_df["Paycom Status"].str.lower().isin(ACTIVE_STATUSES)].copy()

    # Summary
    sum_data = {
        "Metric": [
            "Total Paycom employees",
            "Total UZIO employees",
            "Employees missing in UZIO (Paycom-only)",
            "# mapped fields compared",
            "Total mismatches (mapped only)",
            "Active mismatches (mapped only)"
        ],
        "Value": [
            len(pay_ids),
            len(uz_ids),
            len(pay_ids - uz_ids),
            len(mapping_df),
            len(all_miss_df),
            len(act_miss_df)
        ]
    }
    summary_df = pd.DataFrame(sum_data)

    # Missing in UZIO
    missing_in_uzio_df = pd.DataFrame(columns=["Employee ID", "Status", "First Name", "Last Name", "State", "Position", "Work Location"])
    missing_ids = list(pay_ids - uz_ids)
    if missing_ids:
        m_list = []
        for eid in missing_ids:
            p_i = pay_idx.get(eid)
            m_list.append({
                "Employee ID": eid,
                "Status": str(pay.loc[p_i, paycom_status_col]) if paycom_status_col in pay.columns else "",
                "First Name": str(pay.loc[p_i, paycom_fn_col]) if paycom_fn_col and paycom_fn_col in pay.columns else "",
                "Last Name": str(pay.loc[p_i, paycom_ln_col]) if paycom_ln_col and paycom_ln_col in pay.columns else "",
                "State": str(pay.loc[p_i, paycom_state_col]) if paycom_state_col and paycom_state_col in pay.columns else "",
                "Position": "",
                "Work Location": ""
            })
        missing_in_uzio_df = pd.DataFrame(m_list)

    # Maps
    field_map_df = pd.DataFrame(fields_used)
    filing_ui_df = pd.DataFrame(list(filing_map.items()), columns=["DB Key", "UI Label"])
    norm_rules_df = pd.DataFrame({"Normalization Rules Applied": NORMALIZATION_NOTES})

    return summary_df, act_miss_df, all_miss_df, missing_in_uzio_df, field_map_df, filing_ui_df, norm_rules_df

def build_report_bytes(sum_df, act_df, all_df, miss_df, f_map_df, ui_map_df, rules_df):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        sum_df.to_excel(writer, sheet_name="Summary", index=False)
        act_df.to_excel(writer, sheet_name="Active_Mismatches", index=False)
        all_df.to_excel(writer, sheet_name="All_Mismatches", index=False)
        miss_df.to_excel(writer, sheet_name="Missing_in_UZIO", index=False)
        f_map_df.to_excel(writer, sheet_name="Field_Mapping_Used", index=False)
        ui_map_df.to_excel(writer, sheet_name="FilingStatus_UI_Map", index=False)
        rules_df.to_excel(writer, sheet_name="Normalization_Rules", index=False)

        # Auto format columns
        for sheet in writer.sheets.values():
            for col in sheet.columns:
                max_length = 0
                c = col[0].column_letter
                for cell in col:
                    try: max_length = max(max_length, len(str(cell.value)))
                    except: pass
                sheet.column_dimensions[c].width = min(max_length + 2, 60)
    return out.getvalue()

def render_ui():
    st.title(APP_TITLE)
    client_name = st.text_input("Client Name", value="Client", key="paycom_withholding_client")

    c1, c2 = st.columns(2)
    with c1: paycom_file = st.file_uploader("Paycom export (CSV/XLSX)", type=["csv", "xlsx"])
    with c2: uzio_file = st.file_uploader("UZIO export (CSV/XLSX - long format)", type=["csv", "xlsx"])

    if st.button("Run Audit", type="primary", disabled=not (paycom_file and uzio_file)):
        with st.spinner("Running audit..."):
            try:
                def read_file(f):
                    f.seek(0)
                    if f.name.lower().endswith(".csv"):
                        return pd.read_csv(io.BytesIO(f.getvalue()), dtype=str, keep_default_na=False)
                    return pd.read_excel(io.BytesIO(f.getvalue()), engine="openpyxl", dtype=str, keep_default_na=False)

                paycom_df = read_file(paycom_file)
                uzio_long_df = read_file(uzio_file)
                
                # Fetch mappings from disk to simplify UI
                import os
                
                # For robust path reading, we can use absolute or relative paths:
                base_dir = "Paycom to UZIO withholding"
                # Fallback to local root if shifted later
                mapping_path = os.path.join(base_dir, "Mapping.xlsx")
                yml_path = os.path.join(base_dir, "key_mapping.yml")
                filing_path = os.path.join(base_dir, "filing status_code.txt")
                
                if not os.path.exists(mapping_path): st.error(f"Missing {mapping_path}"); return
                if not os.path.exists(yml_path): st.error(f"Missing {yml_path}"); return
                if not os.path.exists(filing_path): st.error(f"Missing {filing_path}"); return

                mapping_df = _read_mapping_xlsx(mapping_path)

                with open(yml_path, "rb") as f:
                    labels_by_state = _load_key_mapping_yml_bytes(f.read())
                    
                with open(filing_path, "rb") as f:
                    filing_map = _load_filing_status_code_bytes(f.read())

                emp_id_col, status_col, state_col, fn_col, ln_col = _autodetect_paycom_cols(paycom_df)

                s_df, act_df, all_df, miss_df, f_map_df, ui_map_df, rules_df = run_withholding_audit(
                    paycom_df=paycom_df, uzio_long_df=uzio_long_df, mapping_df=mapping_df,
                    labels_by_state=labels_by_state, filing_map=filing_map,
                    paycom_emp_id_col=emp_id_col, paycom_status_col=status_col,
                    paycom_state_col=state_col, paycom_fn_col=fn_col, paycom_ln_col=ln_col
                )

                rep_bytes = build_report_bytes(s_df, act_df, all_df, miss_df, f_map_df, ui_map_df, rules_df)

                st.success("Report generated successfully.")
                timestamp = pd.Timestamp.now().strftime('%d_%m_%Y_%H%M')
                st.download_button(
                    label="Download Audit Report",
                    data=rep_bytes,
                    file_name=f"{client_name}_Uzio_Paycom_Withholding_Audit_Report_{timestamp}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

                st.subheader("Summary (preview)")
                st.dataframe(s_df, use_container_width=True)

            except Exception as e:
                st.error(f"Error: {e}")
                st.exception(e)

if __name__ == "__main__":
    st.set_page_config(layout="wide")
    render_ui()
