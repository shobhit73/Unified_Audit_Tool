import streamlit as st
import pandas as pd
import io
import re
import yaml
from datetime import datetime

# =====================================================================
# ADP <-> UZIO Withholding Audit Tool (Standalone)
# =====================================================================

def is_active_status(status_str):
    if not status_str:
        return True # Default to active if unknown
    s = str(status_str).lower().strip()
    # Broadly identify active statuses
    if s in {"active", "active employee", "a", "act", "active (current)"}:
        return True
    if s.startswith("act"):
        return True
    return False

# 1. Filing Status Dictionary Built-in (from filing status_code.txt)
FILING_STATUS_MAP = {
    "FEDERAL_SINGLE": "Single",
    "FEDERAL_MARRIED": "Married",
    "FEDERAL_MARRIED_SINGLE": "Married but withhold as Single",
    "MD_SINGLE": "Single",
    "MD_MARRIED": "Married",
    "MD_MARRIED_SINGLE": "Married but withhold at single rate",
    "DC_SINGLE": "Single",
    "DC_MARRIED_DP_JOINTLY": "Married/Domestic Partners Filing Jointly",
    "DC_MARRIED_SEPARATELY": "Married Filing Separately",
    "DC_HEAD_OF_HOUSEHOLD": "Head of Household",
    "DC_MARRIED_DP_SEPARATELY": "Married/Domestic Partners Filing Separately",
    "FEDERAL_SINGLE_OR_MARRIED": "Single or Married filing separately",
    "FEDERAL_MARRIED_JOINTLY": "Married filing jointly or Qualifying surviving spouse",
    "FEDERAL_HEAD_OF_HOUSEHOLD": "Head of household",
    "NM_SINGLE": "Single or Married filing separately",
    "NM_MARRIED": "Married filing jointly or Qualifying Surviving Spouse",
    "NM_MARRIED_SINGLE": "Married but withhold as Single",
    "NM_HEAD_OF_HOUSEHOLD": "Head of Household",
    "MS_SINGLE": "Single",
    "MS_HEAD_OF_HOUSEHOLD": "Head of Family",
    "MS_M1": "Married (Spouse NOT employed)",
    "MS_M2": "Married (Spouse is employed)",
    "MO_SINGLE": "Single or Married Spouse Works or Married Filing Separate",
    "MO_MARRIED": "Married (Spouse does not work)",
    "MO_HEAD_OF_HOUSEHOLD": "Head of Household",
    "AL_NO_PERSONAL_EXEMPTION": "No Personal Exemption",
    "AL_SINGLE": "Single",
    "AL_MARRIED": "Married",
    "AL_MARRIED_SEPARATELY": "Married Filing Separately",
    "AL_HEAD_OF_HOUSEHOLD": "Head of Family",
    "DE_MARRIED": "Married",
    "DE_SINGLE": "Single",
    "DE_MARRIED_SINGLE_RATE": "Married but Withhold as Single",
    "OK_MARRIED": "Married",
    "OK_SINGLE": "Single",
    "OK_MARRIED_SINGLE_RATE": "Married but Withhold as Single",
    "OK_NRA": "Non-Resident Alien",
    "NC_HEAD_OF_HOUSEHOLD": "Head of Household",
    "NC_MARRIED": "Married Filing Jointly or Surviving Spouse",
    "NC_SINGLE": "Single or Married Filing Separately",
    "SC_MARRIED_SINGLE_RATE": "Married but Withhold at higher Single Rate",
    "SC_MARRIED": "Married",
    "SC_SINGLE": "Single",
    "UT_SINGLE": "Single or Married filing separately",
    "UT_MARRIED": "Married filing jointly or Qualifying widow(er)",
    "UT_HEAD_OF_HOUSEHOLD": "Head of Household",
    "GA_SINGLE": "Single",
    "GA_SEPARATE_MARRIED_JOINT_BOTH_WORKING": "Married Filing Separate or Married Filing Joint both spouses working",
    "GA_MARRIED_JOINT_ONE_WORKING": "Married Filing Joint one spouse working",
    "GA_HEAD_OF_HOUSEHOLD": "Head of Household",
    "WI_SINGLE": "Single",
    "WI_MARRIED": "Married",
    "WI_MARRIED_SINGLE_RATE": "Married but withhold at higher single rate",
    "KS_SINGLE": "Single",
    "KS_JOINT": "Joint",
    "VT_SINGLE": "Single",
    "VT_MARRIED": "Married/Civil Union Filing Jointly",
    "VT_MARRIED_FILING_SEPERATELY": "Married/Civil Union Filing Separately",
    "VT_MARRIED_SINGLE_RATE": "Married, but withhold at higher single rate",
    "NJ_SINGLE": "Single",
    "NJ_MARRIED_DP_JOINTLY": "Married/Civil Union Couple Joint",
    "NJ_MARRIED_SEPARATELY": "Married/Civil Union Partner Separate",
    "NJ_HEAD_OF_HOUSEHOLD": "Head of Household",
    "NJ_QUALIFIED_WIDOW": "Qualifying Widow(er)/Surviving Civil Union Partner",
    "CA_HEAD_OF_HOUSEHOLD": "Head of Household",
    "CA_MARRIED": "Married (one income)",
    "CA_SINGLE": "Single or Married (with two or more incomes)",
    "MN_SINGLE": "Single, Married but legally separated or Spouse is a nonresident alien",
    "MN_MARRIED": "Married",
    "IA_OTHER": "Other (Including Single)",
    "IA_HEAD_OF_HOUSEHOLD": "Head of Household",
    "IA_MARRIED_JOINTLY": "Married filing jointly",
    "IA_QUALIFIED_SPOUSE": "Qualifying Surviving Spouse",
    "ME_SINGLE": "Single or Head of Household",
    "ME_MARRIED": "Married",
    "ME_MARRIED_SINGLE_RATE": "Married but withhold at higher single rate",
    "ME_NON_RESIDENT_ALIEN": "Nonresident alien",
    "MN_MARRIED_SINGLE_RATE": "Married but withhold at higher single rate",
    "NY_MARRIED_WITHHOLD_SINGLE": "Married but withhold as Single",
    "NY_SINGLE": "Single",
    "NY_MARRIED": "Married",
    "NY_HEAD_OF_HOUSEHOLD": "Head of Household",
    "NE_SINGLE": "Single",
    "NE_MARRIED": "Married Filing Jointly or Qualifying Widow(er)",
    "LA_NO_DEDUCTION": "No Deduction",
    "LA_SINGLE_OR_MARRIED": "Single or married filing separately",
    "LA_MARRIED_FILING_JOINTLY_HOH": "Married filing jointly, qualifying surviving spouse, or head of household",
    "OR_SINGLE": "Single",
    "OR_MARRIED": "Married",
    "OR_MARRIED_SINGLE_RATE": "Married but withhold at higher single rate",
    "ND_SINGLE": "Single",
    "ND_MARRIED": "Married",
    "ND_MARRIED_SINGLE_RATE": "Married but Withhold at higher Single Rate",
    "ND_SINGLE_MARRIED_SEPARATELY": "Single or Married filing separately",
    "ND_HEAD_OF_HOUSEHOLD": "Head of household",
    "ND_MARRIED_JOINTLY": "Married filing jointly  or Qualifying Surviving Spouse",
    "ID_SINGLE": "Single",
    "ID_MARRIED": "Married",
    "ID_MARRIED_SINGLE_RATE": "Married but Withhold at higher Single Rate",
    "CO_SINGLE_OR_MARRIED_SEPARATELY": "Single or Married filing separately",
    "CO_MARRIED_JOINTLY": "Married filing jointly",
    "CO_HEAD_OF_HOUSEHOLD": "Head of household",
    "CO_SINGLE": "Single",
    "CO_MARRIED": "Married",
    "CO_MARRIED_SINGLE_RATE": "Married but Withhold at higher Single Rate",
    "HI_SINGLE": "Single",
    "HI_MARRIED": "Married",
    "HI_MARRIED_SINGLE_RATE": "Married but Withhold at higher single rate",
    "HI_DISABLED": "Certified disabled person",
    "HI_NMS": "Nonresident Military Spouse",
    "MT_SINGLE": "Single or Married filing separately",
    "MT_MARRIED": "Married filing jointly or qualifying surviving spouse",
    "MT_HEAD_OF_HOUSEHOLD": "Head of household",
    "AR_SINGLE": "Single",
    "AR_MARRIED_FILING_JOINTLY": "Married Filing Jointly",
    "AR_HOH": "Head of Household"
}

# 2. Hardcoded Columns Mapping
FIELD_MAPPING = [
    {"UZIO": "employee_id", "ADP": "Associate ID"},
    {"UZIO": "employee_first_name", "ADP": "Legal First Name"},
    {"UZIO": "employee_last_name", "ADP": "Legal Last Name"},
    {"UZIO": "FIT_WITHHOLDING_EXEMPTION", "ADP": "Do Not Calculate Federal Income Tax"},
    {"UZIO": "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD", "ADP": "Federal Additional Tax Amount"},
    {"UZIO": "FIT_FILING_STATUS", "ADP": "Federal/W4 Marital Status Description"},
    {"UZIO": "FIT_CHILD_AND_DEPENDENT_TAX_CREDIT", "ADP": "Dependents"},
    {"UZIO": "FIT_DEDUCTIONS_OVER_STANDARD", "ADP": "Deductions"},
    {"UZIO": "FIT_HIGHER_WITHHOLDING", "ADP": "Multiple Jobs indicator"},
    {"UZIO": "FIT_OTHER_INCOME", "ADP": "Other Income"},
    {"UZIO": "FIT_WITHHOLD_AS_NON_RESIDENT", "ADP": "Non-Resident Alien"},
    {"UZIO": "FIT_WITHHOLDING_ALLOWANCE", "ADP": "Federal/W4 Exemptions"},
    {"UZIO": "SIT_WITHHOLDING_EXEMPTION", "ADP": "Do not calculate State Tax"},
    {"UZIO": "SIT_FILING_STATUS", "ADP": "State Marital Status Description"},
    {"UZIO": "SIT_TOTAL_ALLOWANCES", "ADP": "State Exemptions/Allowances"},
    {"UZIO": "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD", "ADP": "State Additional Tax Amount"},
]

MONEY_CENTS_FIELDS = {
    "FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD",
    "FIT_CHILD_AND_DEPENDENT_TAX_CREDIT",
    "FIT_DEDUCTIONS_OVER_STANDARD",
    "FIT_OTHER_INCOME",
    "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"
}

def load_key_mapping_yml():
    try:
        with open("key_mapping.yml", "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        labels = {}
        for _, items in data.get("withholding_es", {}).get("mappings", {}).items():
            if not isinstance(items, dict):
                continue
            for k, meta in items.items():
                if isinstance(meta, dict) and "label" in meta:
                    labels[k] = str(meta["label"])
        return labels
    except Exception:
        return {}

def _clean(x):
    if pd.isna(x) or x is None:
        return ""
    return str(x).strip()

def get_field_label(key, labels_map):
    if key in labels_map:
        return labels_map[key]
    return key.replace("_", " ").title()

def determine_jurisdiction(key):
    if key.startswith("FIT_"):
        return "FED"
    # Fallback for SIT, we'd need employee state, but FED works for FIT
    return ""

def _parse_date(d_str):
    if not d_str:
        return pd.NaT
    try:
        return pd.to_datetime(d_str)
    except:
        return pd.NaT

def apply_latest_effective_date(adp_df, emp_id_col):
    if "Federal/W4 Effective Date" not in adp_df.columns:
        adp_df["_eff_date"] = pd.NaT
        adp_df["IS_SELECTED_LATEST"] = True
        return adp_df, pd.DataFrame()

    adp_df["_eff_date"] = adp_df["Federal/W4 Effective Date"].apply(_parse_date)
    
    # Sort by emp_id, then _eff_date descending, then take first
    adp_df_sorted = adp_df.sort_values([emp_id_col, "_eff_date"], ascending=[True, False], na_position='last')
    adp_df_dedup = adp_df_sorted.drop_duplicates(subset=[emp_id_col], keep="first").copy()
    
    adp_df_dedup["IS_SELECTED_LATEST"] = True
    
    # Build date dataframe to show
    adp_dates = adp_df_sorted.copy()
    adp_dates["IS_SELECTED_LATEST"] = adp_dates.index.isin(adp_df_dedup.index)
    
    cols_to_keep = [c for c in [emp_id_col, "Legal First Name", "Legal Last Name", "Federal/W4 Effective Date", "_eff_date", "IS_SELECTED_LATEST"] if c in adp_dates.columns]
    
    date_report = adp_dates[cols_to_keep].copy()
    if "_eff_date" in date_report.columns:
        date_report.rename(columns={"_eff_date": "EFF_DATE"}, inplace=True)
    return adp_df_dedup, date_report

# Comparison Rules
def _norm_filing_status(s):
    s = _clean(s).lower()
    return re.sub(r'[\W_]+', ' ', s).strip()

def _norm_bool(s):
    s = str(s).strip().lower()
    if s in {"yes", "y", "true", "1", "on"}:
        return "1"
    if s in {"no", "n", "false", "0", "off"}:
        return "0"
    return ""  

def _norm_float(s):
    s = str(s).replace("$", "").replace(",", "").strip()
    if s == "":
        return None
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except:
        return None

def compare_values(uz_key, adp_val_raw, uz_val_raw, filing_status_map):
    araw = _clean(adp_val_raw)
    uraw = _clean(uz_val_raw)
    
    # BOOLEAN logic (typically Exemption or Multiple Jobs)
    if "EXEMPTION" in uz_key or "HIGHER_WITHHOLDING" in uz_key:
        ab = _norm_bool(araw)
        ub = _norm_bool(uraw)
        if ab == "" and araw == "":
            ab = "0"  # ADP blank treated as False
        if ub == "" and uraw == "":
            ub = "0"
        
        match = (ab == ub)
        return match, ab, ub, "bool_blank_false", "ADP Yes/No vs UZIO True/False; blank treated as False"
        
    # FILING STATUS logic
    if "FILING_STATUS" in uz_key:
        if uraw in filing_status_map:
            u_mapped = filing_status_map[uraw]
        else:
            # Fallback label logic for unknown states (e.g. IL_SINGLE -> Single)
            u_mapped = uraw.split("_", 1)[1].replace("_", " ").title() if "_" in uraw else uraw.title()
            
        a_n = _norm_filing_status(araw)
        u_n = _norm_filing_status(u_mapped)
        
        match = (a_n == u_n) or (a_n and a_n in u_n) or (u_n and u_n in a_n)
        return match, a_n, u_n, "filing_status", "UZIO enum mapped to ADP label via filing status mapping"
        
    # MONEY CENTS logic
    if uz_key in MONEY_CENTS_FIELDS:
        af = _norm_float(araw)
        uf = _norm_float(uraw)
        
        af_val = af if af is not None else 0.0
        uf_val = (uf / 100.0) if uf is not None else 0.0
        
        match = (abs(af_val - uf_val) < 0.01)
        a_out = "0" if af is None and araw=="" else (str(int(af_val)) if af_val.is_integer() else str(af_val))
        u_out = "0" if uf is None and uraw=="" else (str(int(uf_val)) if uf_val.is_integer() else str(uf_val))
        return match, a_out, u_out, "money_cents", "UZIO stored in cents; compared in dollars"
        
    # INTEGER / DEFAULT logic
    af = _norm_float(araw)
    uf = _norm_float(uraw)
    
    af_val = af if af is not None else 0.0
    uf_val = uf if uf is not None else 0.0
    
    match = (af_val == uf_val)
    a_out = "0" if af is None and araw=="" else (str(int(af_val)) if af_val.is_integer() else str(af_val))
    u_out = "0" if uf is None and uraw=="" else (str(int(uf_val)) if uf_val.is_integer() else str(uf_val))
    return match, a_out, u_out, "int_blank_zero", "Numeric; blank treated as 0"


def render_ui():
    st.title("ADP ↔ UZIO Withholding Audit Tool")
    
    st.markdown("""
    **Inputs**
    - **ADP Export** (CSV/XLSX) – wide format (one row per employee)
    - **UZIO Withholding Export** (CSV/XLSX) – long format with: `employee_id`, `withholding_field_key`, `withholding_field_value`
    """)

    adp_file = st.file_uploader("Upload ADP File", type=["csv", "xlsx", "xls"], key="adp_file")
    uzio_file = st.file_uploader("Upload UZIO Withholding File", type=["csv", "xlsx", "xls"], key="uzio_file")
    client_name = st.text_input("Enter Client Name (for Report Filename)", value="Client_Name")

    if st.button("Run Audit", type="primary", disabled=not (adp_file and uzio_file)):
        with st.spinner("Processing..."):
            try:
                def read_file(f):
                    if f.name.lower().endswith(".csv"):
                        return pd.read_csv(io.BytesIO(f.getvalue()), dtype=str)
                    return pd.read_excel(io.BytesIO(f.getvalue()), engine="openpyxl", dtype=str)
                    
                adp_df = read_file(adp_file)
                uzio_df = read_file(uzio_file)
                
                # Check column headers for auto-detect
                adp_cols = [c for c in adp_df.columns]
                uzio_cols = [c for c in uzio_df.columns]
                
                adp_id_col = next((c for c in adp_cols if c.strip().lower() in ["associate id", "employee id", "employee_id", "emp_id"]), adp_cols[0])
                uzio_id_col = next((c for c in uzio_cols if c.strip().lower() in ["employee_id", "employee id", "emp_id"]), uzio_cols[0])
                
                # Apply Effective Date logic to ADP
                adp_df_dedup, date_report = apply_latest_effective_date(adp_df, adp_id_col)
                adp_df_dedup[adp_id_col] = adp_df_dedup[adp_id_col].astype(str).apply(_clean)
                adp_df_dedup = adp_df_dedup[adp_df_dedup[adp_id_col] != ""]
                
                # Pivot UZIO
                uzio_df[uzio_id_col] = uzio_df[uzio_id_col].astype(str).apply(_clean)
                uzio_df = uzio_df[uzio_df[uzio_id_col] != ""]
                uzio_key_col = next((c for c in uzio_cols if c.strip().lower() in ["withholding_field_key", "field_key", "key"]), "withholding_field_key")
                uzio_val_col = next((c for c in uzio_cols if c.strip().lower() in ["withholding_field_value", "field_value", "value"]), "withholding_field_value")
                
                uzio_wide = uzio_df.pivot_table(
                    index=uzio_id_col, 
                    columns=uzio_key_col, 
                    values=uzio_val_col, 
                    aggfunc=lambda x: list(x)[-1]
                ).reset_index()
                
                # Additional Name/Status columns if available from long format
                fn_col = next((c for c in uzio_cols if c.strip().lower() in ["employee_first_name", "first_name"]), None)
                ln_col = next((c for c in uzio_cols if c.strip().lower() in ["employee_last_name", "last_name"]), None)
                status_uz_col = next((c for c in uzio_cols if c.strip().lower() == "status"), None)
                
                cols_to_get = []
                if fn_col: cols_to_get.append(fn_col)
                if ln_col: cols_to_get.append(ln_col)
                if status_uz_col: cols_to_get.append(status_uz_col)
                
                if cols_to_get:
                    names_df = uzio_df.groupby(uzio_id_col)[cols_to_get].first().reset_index()
                    uzio_wide = uzio_wide.merge(names_df, on=uzio_id_col, how="left")
                
                # Identify Active / Terminated

                # We need to be careful: "Marital Status" or "Tax Status" columns shouldn't be picked for employment status
                def find_status_col(cols):
                    # Priority 1: Exact matches or well-known status headers
                    priority = ["worker status", "employment status", "associate status", "status description"]
                    for c in cols:
                        if c.lower().strip() in priority:
                            return c
                    # Priority 2: Substring matches excluding noise
                    for c in cols:
                        cl = c.lower()
                        if "status" in cl and "marital" not in cl and "tax" not in cl and "withholding" not in cl:
                            return c
                    return None

                status_col = find_status_col(adp_cols)
                
                if status_col:
                    adp_df_dedup["_IS_ACTIVE"] = adp_df_dedup[status_col].apply(is_active_status)
                    adp_df_dedup["_STATUS"] = adp_df_dedup[status_col]
                else:
                    adp_df_dedup["_IS_ACTIVE"] = None
                    adp_df_dedup["_STATUS"] = ""
                
                name_col1 = next((c for c in adp_cols if "first" in c.lower()), None)
                name_col2 = next((c for c in adp_cols if "last" in c.lower()), None)
                if name_col1 and name_col2:
                    adp_df_dedup["_NAME"] = adp_df_dedup[name_col1].astype(str) + " " + adp_df_dedup[name_col2].astype(str)
                else:
                    adp_df_dedup["_NAME"] = ""
                    
                adp_state_col = next((c for c in adp_cols if c.strip().lower() in ["worked in state", "state", "work state", "state code"]), None)
                
                merg = pd.merge(adp_df_dedup, uzio_wide, left_on=adp_id_col, right_on=uzio_id_col, how="outer", indicator=True)
                
                missing_in_uzio = merg[merg["_merge"] == "left_only"].copy()
                missing_in_adp = merg[merg["_merge"] == "right_only"].copy()
                both = merg[merg["_merge"] == "both"].copy()
                
                # Fallback to UZIO status if ADP status is missing
                if status_uz_col and status_uz_col in both.columns:
                    both["_IS_ACTIVE"] = both["_IS_ACTIVE"].fillna(both[status_uz_col].astype(str).str.upper() == "ACTIVE")
                    both["_STATUS"] = both["_STATUS"].replace("", pd.NA).fillna(both[status_uz_col])
                both["_IS_ACTIVE"] = both["_IS_ACTIVE"].fillna(True)
                
                adp_map = {m["UZIO"]: m["ADP"] for m in FIELD_MAPPING}
                
                labels = load_key_mapping_yml()
                
                mismatches = []
                rules_tracked = {}
                
                for idx, row in both.iterrows():
                    emp_id = row[adp_id_col]
                    emp_name = row["_NAME"]
                    emp_status = "ACTIVE" if row["_IS_ACTIVE"] else "TERMINATED"
                    # Handle raw status if present but not strictly active
                    if row["_STATUS"] and not row["_IS_ACTIVE"]:
                        emp_status = str(row["_STATUS"]).upper()
                        
                    state_code = row[adp_state_col] if adp_state_col else ""
                    eff_date = str(row["_eff_date"])[:10] if pd.notna(row["_eff_date"]) else ""

                    for uz_key, adp_col in adp_map.items():
                        if adp_col not in both.columns or uz_key not in uzio_wide.columns:
                            continue
                        
                        a_raw = row[adp_col] if pd.notna(row[adp_col]) else ""
                        u_raw = row[uz_key] if pd.notna(row.get(uz_key)) else ""
                        
                        # IL Special Handling
                        if uz_key == "SIT_TOTAL_ALLOWANCES":
                            u_computed_raw = u_raw
                            rule_str = "Compare ADP State Exemptions/Allowances to UZIO SIT_TOTAL_ALLOWANCES"
                            c_type = "allowances_calc"
                            
                            # If total allowances is missing in UZIO but basic/addl exists (IL pattern)
                            if u_computed_raw == "" and ("SIT_BASIC_ALLOWANCES" in row or "SIT_ADDITIONAL_ALLOWANCES" in row):
                                u_basic = _norm_float(row.get("SIT_BASIC_ALLOWANCES", ""))
                                u_addl = _norm_float(row.get("SIT_ADDITIONAL_ALLOWANCES", ""))
                                if u_basic is not None or u_addl is not None:
                                    u_computed_raw = str(int((u_basic or 0) + (u_addl or 0)))
                                    rule_str = "Compare ADP State Exemptions/Allowances to UZIO SIT_TOTAL_ALLOWANCES if present else SIT_BASIC_ALLOWANCES+SIT_ADDITIONAL_ALLOWANCES"
                                    
                            match, a_n, u_n, _, _ = compare_values(uz_key, a_raw, u_computed_raw, FILING_STATUS_MAP)
                            u_raw_display = u_computed_raw if u_raw == "" else u_raw
                            uzio_field_display = "SIT_BASIC_ALLOWANCES+SIT_ADDITIONAL_ALLOWANCES" if u_raw == "" and u_computed_raw != "" else uz_key
                        else:
                            match, a_n, u_n, c_type, rule_str = compare_values(uz_key, a_raw, u_raw, FILING_STATUS_MAP)
                            u_raw_display = u_raw
                            uzio_field_display = uz_key
                            
                        # Record rule explicitly for Field Mapping Rules sheet
                        if uz_key not in rules_tracked:
                            rules_tracked[uz_key] = {
                                "FIELD_LABEL": get_field_label(uz_key, labels),
                                "FIELD_KEY": uz_key,
                                "JURISDICTION": determine_jurisdiction(uz_key),
                                "ADP_COLUMN": adp_col,
                                "ADP_COLUMN_STD": adp_col.replace(" ", "_").upper(),
                                "COMPARISON_TYPE": c_type,
                                "RULE_APPLIED": rule_str
                            }
                        
                        if not match:
                            mismatches.append({
                                "EMPLOYEE_ID": emp_id,
                                "EMPLOYEE_NAME": emp_name,
                                "EMPLOYMENT_STATUS": emp_status,
                                "STATE_CODE": state_code,
                                "FIELD_LABEL": get_field_label(uz_key, labels),
                                "FIELD_KEY": uz_key,
                                "ADP_COLUMN": adp_col,
                                "UZIO_FIELD": uzio_field_display,
                                "ADP_VALUE_RAW": a_raw,
                                "UZIO_VALUE_RAW": u_raw_display,
                                "ADP_VALUE_NORMALIZED": a_n,
                                "UZIO_VALUE_NORMALIZED": u_n,
                                "RULE_APPLIED": rule_str,
                                "ADP_EFFECTIVE_DATE_USED": eff_date
                            })
                
                # DataFrames Compilation
                df_miss_all = pd.DataFrame(mismatches)
                if df_miss_all.empty:
                    df_miss_all = pd.DataFrame(columns=[
                        "EMPLOYEE_ID", "EMPLOYEE_NAME", "EMPLOYMENT_STATUS", "STATE_CODE",
                        "FIELD_LABEL", "FIELD_KEY", "ADP_COLUMN", "UZIO_FIELD",
                        "ADP_VALUE_RAW", "UZIO_VALUE_RAW", "ADP_VALUE_NORMALIZED", 
                        "UZIO_VALUE_NORMALIZED", "RULE_APPLIED", "ADP_EFFECTIVE_DATE_USED"
                    ])
                    
                df_miss_active = df_miss_all[df_miss_all["EMPLOYMENT_STATUS"] == "ACTIVE"].copy() if not df_miss_all.empty else df_miss_all.copy()
                df_miss_term = df_miss_all[df_miss_all["EMPLOYMENT_STATUS"] != "ACTIVE"].copy() if not df_miss_all.empty else df_miss_all.copy()
                
                # Mismatch Summary
                if not df_miss_all.empty:
                    df_sum = df_miss_all.groupby(["FIELD_LABEL", "FIELD_KEY"]).agg(
                        mismatch_rows=("EMPLOYEE_ID", "count"),
                        employees_affected=("EMPLOYEE_ID", "nunique")
                    ).reset_index()
                else:
                    df_sum = pd.DataFrame(columns=["FIELD_LABEL", "FIELD_KEY", "mismatch_rows", "employees_affected"])
                    
                # Employees with Mismatches
                if not df_miss_all.empty:
                    df_emp_sum = df_miss_all.groupby("EMPLOYEE_ID").agg(
                        EMPLOYEE_NAME=("EMPLOYEE_NAME", "first"),
                        EMPLOYMENT_STATUS=("EMPLOYMENT_STATUS", "first"),
                        STATE_CODE=("STATE_CODE", "first"),
                        mismatch_rows=("FIELD_KEY", "count"),
                        fields=("FIELD_LABEL", lambda x: ", ".join(sorted(set(x))))
                    ).reset_index()
                else:
                    df_emp_sum = pd.DataFrame(columns=["EMPLOYEE_ID", "EMPLOYEE_NAME", "EMPLOYMENT_STATUS", "STATE_CODE", "mismatch_rows", "fields"])
                    
                # Field Mapping Rules
                df_rules = pd.DataFrame(list(rules_tracked.values()))
                
                # Top Summary
                uz_id_list = uzio_df[uzio_id_col].dropna().unique()
                uz_total = len(uz_id_list)
                
                # Use explicit boolean comparison to avoid bitwise NOT (~) errors with numeric-like booleans
                is_active_mask = (both["_IS_ACTIVE"] == True)
                uz_active_guess = int(is_active_mask.sum())
                uz_term_guess = len(both) - uz_active_guess
                
                metrics = [
                    {"Metric": "UZIO employees (total)", "Value": uz_total},
                    {"Metric": "UZIO employees (Active)", "Value": uz_active_guess},
                    {"Metric": "UZIO employees (Terminated)", "Value": uz_term_guess},
                    {"Metric": "ADP employees compared (unique IDs)", "Value": len(both)},
                    {"Metric": "Mismatch rows (All)", "Value": len(df_miss_all)},
                    {"Metric": "Mismatch rows (Active)", "Value": len(df_miss_active)},
                    {"Metric": "Mismatch rows (Terminated)", "Value": len(df_miss_term)},
                    {"Metric": "Employees with ≥1 mismatch", "Value": df_miss_all["EMPLOYEE_ID"].nunique() if not df_miss_all.empty else 0},
                    {"Metric": "ADP duplicate IDs in compared set", "Value": len(adp_df) - len(adp_df_dedup)},
                    {"Metric": "Employees missing in UZIO", "Value": len(missing_in_uzio)},
                    {"Metric": "Employees missing in ADP", "Value": len(missing_in_adp)},
                    {"Metric": "Unverified fields", "Value": 1}
                ]
                df_metrics = pd.DataFrame(metrics)
                
                # Missing Sheets
                cols_adp_missing = [c for c in missing_in_adp.columns if c in uzio_df.columns]
                df_missing_adp = missing_in_adp[cols_adp_missing].copy()
                
                df_missing_uzio = pd.DataFrame(columns=["ASSOCIATE_ID", "LEGAL_FIRST_NAME", "LEGAL_LAST_NAME"])
                if not missing_in_uzio.empty:
                    fnc = name_col1 if name_col1 else ""
                    lnc = name_col2 if name_col2 else ""
                    df_missing_uzio["ASSOCIATE_ID"] = missing_in_uzio[adp_id_col]
                    df_missing_uzio["LEGAL_FIRST_NAME"] = missing_in_uzio[fnc] if fnc else ""
                    df_missing_uzio["LEGAL_LAST_NAME"] = missing_in_uzio[lnc] if lnc else ""

                # Write to Excel
                timestamp = pd.Timestamp.now().strftime('%d_%m_%Y_%H%M')
                filename = f"ADP_vs_UZIO_FIT_SIT_Mismatch_Report_{client_name}_{timestamp}.xlsx"
                
                out = io.BytesIO()
                with pd.ExcelWriter(out, engine="openpyxl") as writer:
                    df_metrics.to_excel(writer, sheet_name="Summary", index=False)
                    df_sum.to_excel(writer, sheet_name="Mismatch Summary", index=False)
                    df_miss_all.to_excel(writer, sheet_name="Mismatches (All)", index=False)
                    df_miss_active.to_excel(writer, sheet_name="Mismatches (Active)", index=False)
                    df_miss_term.to_excel(writer, sheet_name="Mismatches (Terminated)", index=False)
                    df_emp_sum.to_excel(writer, sheet_name="Employees with Mismatches", index=False)
                    df_rules.to_excel(writer, sheet_name="Field Mapping Rules", index=False)
                    date_report.to_excel(writer, sheet_name="ADP Effective Date Used", index=False)
                    df_missing_adp.to_excel(writer, sheet_name="Missing in ADP", index=False)
                    df_missing_uzio.to_excel(writer, sheet_name="Missing in UZIO (Sample)", index=False)

                    # Auto-width formatting
                    for sheet in writer.sheets:
                        ws = writer.sheets[sheet]
                        for col in ws.columns:
                            max_length = 0
                            column = col[0].column_letter # Get the column name
                            for cell in col:
                                try:
                                    if len(str(cell.value)) > max_length:
                                        max_length = len(cell.value)
                                except:
                                    pass
                            adjusted_width = (max_length + 2)
                            ws.column_dimensions[column].width = min(adjusted_width, 60)

                st.success("Audit Completed Successfully!")
                st.download_button(
                    label="Download Report",
                    data=out.getvalue(),
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
            except Exception as e:
                st.error(f"Error: {e}")
                st.exception(e)

if __name__ == "__main__":
    st.set_page_config(layout="wide")
    render_ui()
