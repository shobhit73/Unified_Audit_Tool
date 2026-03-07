# app.py
import io
import re
from datetime import datetime, date

import numpy as np
import pandas as pd
import streamlit as st
from utils.audit_utils import (
    read_uzio_raw_file,
    HOURLY_ONLY_JOB_TITLES, is_hourly_only_job_title
)

# =========================================================
# Paycom vs UZIO – Census Audit Tool
# - User uploads Raw Uzio Export (.xlsm) and Raw Paycom Export (.csv)
# - Hardcoded mappings
# =========================================================

APP_TITLE = "Paycom Uzio Census Audit Tool"

# Hardcoded Mapping: Internal Standard Name -> Paycom Column Name
PAYCOM_FIELD_MAP = {
    'Employee ID': 'Employee_Code',
    'First Name': 'Legal_Firstname',
    'Last Name': 'Legal_Lastname',
    'Middle Initial': 'Legal_Middle_Name',
    'Employment Status': 'Employee_Status',
    'Hire Date': 'Most_Recent_Hire_Date',
    'Original Hire Date': 'Hire Date',
    'Termination Date': 'Termination_Date',
    # 'Termination Reason': 'Termination_Reason', # Not in sample file
    'Pay Type': 'Pay_Type',
    'Annual Salary': 'Annual_Salary',
    'Hourly Pay Rate': 'Rate_1',
    'Working Hours': 'Scheduled_Pay_Period_Hours',
    'Job Title': 'Position',
    'Department': 'Department_Desc',
    'Work Email': 'Work_Email',
    'Personal Email': 'Personal_Email',
    'Phone Number': 'Primary_Phone',
    'SSN': 'SS_Number',
    'DOB': 'Birth_Date_(MM/DD/YYYY)',
    'Gender': 'Gender',
    'Tobacco User': 'Tobacco_User',
    'FLSA Classification': 'Exempt_Status',
    'Address Line 1': 'Primary_Address_Line_1',
    'Address Line 2': 'Primary_Address_Line_2',
    'City': 'Primary_City/Municipality',
    'Zip': 'Primary_Zip/Postal_Code',
    'State': 'Primary_State/Province',
    'Mailing Address Line 1': 'Mailing_Address_Line_1',
    'Mailing Address Line 2': 'Mailing_Address_Line_2',
    'Mailing City': 'Mailing_City/Municipality',
    'Mailing Zip': 'Mailing_Zip/Postal_Code',
    'Mailing State': 'Mailing_State/Province',
    'License Number': 'DriversLicense',
    'License Expiration Date': 'DLExpirationDate',
}

# ---------- Helpers ----------
def norm_colname(c: str) -> str:
    if c is None:
        return ""
    c = str(c).replace("\n", " ").replace("\r", " ")
    c = c.replace("\u00A0", " ")
    c = c.replace("’", "'").replace("“", '"').replace("”", '"')
    # Remove bracketed suffixes like (Personal Profile) or (Employment Profile - Pay Rates)
    c = re.sub(r'\(.*?\)', '', c)
    c = re.sub(r"\s+", " ", c).strip()
    c = c.replace("*", "")
    c = c.strip('"').strip("'")
    return c

def norm_blank(x):
    if x is None:
        return ""
    if isinstance(x, float) and np.isnan(x):
        return ""
    if isinstance(x, str) and x.strip().lower() in {"", "nan", "none", "null"}:
        return ""
    return x

def find_col(df_cols, *candidate_names):
    norm_map = {norm_colname(c).casefold(): c for c in df_cols}
    for cand in candidate_names:
        key = norm_colname(cand).casefold()
        if key in norm_map:
            return norm_map[key]
    return None

def norm_key_series(s: pd.Series) -> pd.Series:
    s2 = s.astype(object).where(~s.isna(), "")
    def _fix(v):
        v = str(v).strip()
        v = v.replace("\u00A0", " ")
        if re.fullmatch(r"\d+\.0+", v):
            v = v.split(".")[0]
        # Strip leading zeros from purely numeric IDs for matching
        # e.g. "0006" -> "6", "006" -> "6", "0" -> "0"
        if re.fullmatch(r"0+\d+", v):
            v = v.lstrip("0") or "0"
        return v
    return s2.map(_fix)

def try_parse_date(x):
    x = norm_blank(x)
    if x == "":
        return ""
    if isinstance(x, (datetime, date, np.datetime64, pd.Timestamp)):
        return pd.to_datetime(x).strftime("%m/%d/%Y")
    if isinstance(x, str):
        s = x.strip()
        try:
            return pd.to_datetime(s, errors="raise").strftime("%m/%d/%Y")
        except Exception:
            return s
    return str(x)

def as_float_or_none(x):
    x = norm_blank(x)
    if x == "":
        return None
    if isinstance(x, (int, float, np.integer, np.floating)):
        try:
            return float(x)
        except Exception:
            return None
    if isinstance(x, str):
        s = x.strip().replace(",", "").replace("$", "")
        if s == "":
            return None
        try:
            return float(s)
        except Exception:
            return None
    return None

def normalize_space_and_case(x):
    x = norm_blank(x)
    if x == "":
        return ""
    s = str(x).strip()
    s = s.replace("\u00A0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s.casefold()

def normalize_employment_type(x):
    s = normalize_space_and_case(x)
    s = s.replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def normalize_suffix(x):
    s = normalize_space_and_case(x)
    s = re.sub(r"[^a-z0-9]", "", s)  # remove punctuation/spaces
    return s

def normalize_phone(x):
    s = norm_blank(x)
    if s == "":
        return ""
    # remove all non-digits
    digits = re.sub(r"[^0-9]", "", str(s))
    # if 11 digits and starts with 1, remove leading 1
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits

def first_alpha_char(x):
    s = norm_blank(x)
    if s == "":
        return ""
    txt = str(s).strip()
    m = re.search(r"[A-Za-z]", txt)
    return m.group(0).casefold() if m else ""

def normalize_middle_initial(uzio_val, paycom_val):
    # UZIO has 'M', Paycom has 'MICHELLE' => OK if first letter matches
    u = first_alpha_char(uzio_val)
    p = first_alpha_char(paycom_val)
    return u != "" and p != "" and u == p

def canonical_pay_type(x):
    s = normalize_space_and_case(x)
    if s == "":
        return ""
    if "hour" in s:
        return "hourly"
    if "salar" in s or "salary" in s:
        return "salaried"
    return s

def canonical_employment_status(x):
    # Paycom "On Leave" treated as "Active"
    s = normalize_space_and_case(x)
    if s == "":
        return ""
    if "on leave" in s:
        return "active"
    if s in {"active", "activated"}:
        return "active"
    return s

def termination_reason_equal(uzio_val, paycom_val):
    uz = normalize_space_and_case(uzio_val)
    pc = normalize_space_and_case(paycom_val)

    if uz == "" and pc == "":
        return True

    # UZIO "Other" is acceptable for any Paycom reason
    if uz == "other":
        return True

    # If either has involuntary, both must have involuntary
    if ("involuntary" in uz) or ("involuntary" in pc):
        return ("involuntary" in uz) and ("involuntary" in pc)

    # If either has voluntary, both must have voluntary
    if ("voluntary" in uz) or ("voluntary" in pc):
        return ("voluntary" in uz) and ("voluntary" in pc)

    return uz == pc

def resolve_sheet_name(xls: pd.ExcelFile, candidates):
    existing_norm = {norm_colname(s).casefold(): s for s in xls.sheet_names}
    for c in candidates:
        k = norm_colname(c).casefold()
        if k in existing_norm:
            return existing_norm[k]
    return None

def resolve_paycom_col_label(label: str, paycom_cols_all) -> str:
    if label is None:
        return ""
    raw = str(label).strip()
    raw = raw.replace("’", "'").replace("“", '"').replace("”", '"')
    raw = raw.strip().strip(",")
    if raw == "":
        return ""

    pay_norm = {norm_colname(c).casefold(): c for c in paycom_cols_all}

    direct = norm_colname(raw).casefold()
    if direct in pay_norm:
        return pay_norm[direct]

    parts = re.split(r"\(|\)|\bor\b|/|,|;", raw, flags=re.IGNORECASE)
    parts = [norm_colname(p) for p in parts if norm_colname(p)]

    extra = []
    for p in parts:
        extra.extend([norm_colname(x) for x in re.split(r"\s[-–]\s", p) if norm_colname(x)])
    parts = parts + extra

    for p in parts:
        k = norm_colname(p).casefold()
        if k in pay_norm:
            return pay_norm[k]

    for k_norm, actual in pay_norm.items():
        if k_norm and (k_norm in direct or direct in k_norm):
            return actual

    return ""

def read_mapping_sheet(xls: pd.ExcelFile, sheet_name: str, paycom_cols_all: list) -> pd.DataFrame:
    m = pd.read_excel(xls, sheet_name=sheet_name, dtype=object)
    m.columns = [norm_colname(c) for c in m.columns]

    uz_col_name = None
    pc_col_name = None
    for c in m.columns:
        if norm_colname(c).casefold() in {"uzio coloumn", "uzio column"}:
            uz_col_name = c
        if norm_colname(c).casefold() in {"paycom coloumn", "paycom column"}:
            pc_col_name = c

    if uz_col_name is None or pc_col_name is None:
        raise ValueError(f"'{sheet_name}' must contain columns: 'UZIO Column' and 'Paycom Column'.")

    m[uz_col_name] = m[uz_col_name].map(norm_colname)
    m[pc_col_name] = m[pc_col_name].map(norm_colname)

    m = m.dropna(subset=[uz_col_name, pc_col_name]).copy()
    m = m[(m[uz_col_name] != "") & (m[pc_col_name] != "")]
    m = m.drop_duplicates(subset=[uz_col_name], keep="first").copy()

    m["UZIO_Column"] = m[uz_col_name]
    m["PAYCOM_Label"] = m[pc_col_name]
    m["PAYCOM_Resolved_Column"] = m["PAYCOM_Label"].map(lambda x: resolve_paycom_col_label(x, paycom_cols_all))

    # exclude Employee ID/Employee Code from comparisons (key only)
    m["_uz_norm"] = m["UZIO_Column"].map(lambda x: norm_colname(x).casefold())
    m = m[~m["_uz_norm"].isin({"employee id", "employee", "employee_code", "employee code"})].copy()
    m.drop(columns=["_uz_norm"], inplace=True)

    return m

def should_ignore_field_for_paytype(field_name: str, pay_type_canon: str) -> bool:
    """
    Pay-type based ignore rules (as per your requirement):
      - HOURLY employees: ignore annual salary fields
      - SALARIED employees: ignore hourly pay rate AND working hours per week
    """
    f = norm_colname(field_name).casefold()
    pt = (pay_type_canon or "").casefold()

    if pt == "hourly":
        if "annual salary" in f:
            return True

    if pt == "salaried":
        # ignore Hourly Pay Rate (covers: "Hourly Pay Rate", "Hourly Rate", etc.)
        if ("hourly" in f and "rate" in f):
            return True

        # ignore Working Hours per Week (covers: "Working Hours per Week(Digits)", "Hours per Week", etc.)
        if ("hours per week" in f) or ("working hours" in f):
            return True

    return False

def normalized_compare(field_name: str, uzio_val, paycom_val) -> bool:
    f = norm_colname(field_name).casefold()

    if "termination reason" in f:
        return termination_reason_equal(uzio_val, paycom_val)

    if "employment status" in f:
        return canonical_employment_status(uzio_val) == canonical_employment_status(paycom_val)

    if "pay type" in f:
        return canonical_pay_type(uzio_val) == canonical_pay_type(paycom_val)

    if "employment type" in f:
        return normalize_employment_type(uzio_val) == normalize_employment_type(paycom_val)

    if ("middle" in f) and ("initial" in f):
        if normalize_middle_initial(uzio_val, paycom_val):
            return True
        return first_alpha_char(uzio_val) == first_alpha_char(paycom_val)

    if "suffix" in f:
        return normalize_suffix(uzio_val) == normalize_suffix(paycom_val)

    if "ssn" in f:
        # Normalize SSN: digits only, remove leading zeros
        u = re.sub(r"\D", "", str(uzio_val)).lstrip("0")
        p = re.sub(r"\D", "", str(paycom_val)).lstrip("0")
        return u == p

    if "phone" in f:
        # Normalize Phone: digits only, remove leading zeros
        u = normalize_phone(uzio_val).lstrip("0")
        p = normalize_phone(paycom_val).lstrip("0")
        return u == p

    if "zip" in f:
        # Normalize Zip: digits only (simple), remove leading zeros
        u = re.sub(r"\D", "", str(uzio_val)).lstrip("0")
        p = re.sub(r"\D", "", str(paycom_val)).lstrip("0")
        return u == p

    # Date-ish fields (including DOH)
    if any(k in f for k in ["date", "dob", "birth", "effective", "doh", "hire", "termination"]):
        return try_parse_date(uzio_val) == try_parse_date(paycom_val)

    # Numeric-ish fields
    if any(k in f for k in ["salary", "rate", "hours", "amount", "percent", "percentage", "digits"]):
        fa = as_float_or_none(uzio_val)
        fb = as_float_or_none(paycom_val)
        if fa is not None and fb is not None:
            return abs(fa - fb) <= 1e-9
        return normalize_space_and_case(uzio_val) == normalize_space_and_case(paycom_val)

    if "license" in f:
        # Standardize License Number: remove leading zeros
        u = str(uzio_val).strip().lstrip("0")
        p = str(paycom_val).strip().lstrip("0")
        return u == p

    return normalize_space_and_case(uzio_val) == normalize_space_and_case(paycom_val)

# ---------- Core comparison ----------
def run_comparison(uzio_file, paycom_file) -> bytes:
    # 1. Read UZIO Raw
    uzio = read_uzio_raw_file(uzio_file)
    if uzio is None:
        raise ValueError("Failed to read Uzio file.")

    # 2. Read Paycom Raw
    try:
        # Determine encoding or engine
        if paycom_file.name.lower().endswith('.csv'):
             try:
                 paycom = pd.read_csv(paycom_file, dtype=str)
             except UnicodeDecodeError:
                 paycom_file.seek(0)
                 paycom = pd.read_csv(paycom_file, dtype=str, encoding='latin1')
        else:
             paycom = pd.read_excel(paycom_file, dtype=str)
    except Exception as e:
        raise ValueError(f"Failed to read Paycom file: {e}")

    # Normalize Paycom columns
    paycom.columns = [norm_colname(c) for c in paycom.columns]

    # Verify Keys
    UZIO_KEY = 'Employee ID'
    if UZIO_KEY not in uzio.columns:
        raise ValueError(f"Required column '{UZIO_KEY}' not found in Uzio file.")

    PAYCOM_KEY = norm_colname(PAYCOM_FIELD_MAP.get('Employee ID', 'Employee_Code'))
    if PAYCOM_KEY not in paycom.columns:
        raise ValueError(f"Required column '{PAYCOM_KEY}' not found in Paycom file.")

    # --- DISPLAY ID: preserve original leading-zero IDs for output ---
    # Before normalizing, save original keys to build a display map
    uzio_orig_keys = uzio[UZIO_KEY].astype(str).str.strip()
    paycom_orig_keys = paycom[PAYCOM_KEY].astype(str).str.strip()

    # normalize keys (strips leading zeros for matching)
    uzio[UZIO_KEY] = norm_key_series(uzio[UZIO_KEY])
    paycom[PAYCOM_KEY] = norm_key_series(paycom[PAYCOM_KEY])

    # Build display_id_map: normalized_key -> longest original form
    # Prefers Uzio originals (source of truth), then Paycom if longer
    display_id_map = {}
    for norm_val, orig_val in zip(uzio[UZIO_KEY], uzio_orig_keys):
        n = str(norm_val).strip()
        o = str(orig_val).strip()
        if n and (n not in display_id_map or len(o) > len(display_id_map[n])):
            display_id_map[n] = o
    for norm_val, orig_val in zip(paycom[PAYCOM_KEY], paycom_orig_keys):
        n = str(norm_val).strip()
        o = str(orig_val).strip()
        if n and (n not in display_id_map or len(o) > len(display_id_map[n])):
            display_id_map[n] = o

    # Prepare mapping iteration
    # Iterate over PAYCOM_FIELD_MAP keys (Internal Standard Names usually match Uzio columns)
    # Filter out Keys
    mapped_fields = [f for f in PAYCOM_FIELD_MAP.keys() if f != UZIO_KEY]

    # employment status context map (prefer UZIO)
    uzio_emp_status_col = 'Employment Status'
    paycom_emp_status_col = norm_colname(PAYCOM_FIELD_MAP.get('Employment Status', ''))

    uzio_status_map = {}
    if uzio_emp_status_col is not None:
        tmp = uzio[[UZIO_KEY, uzio_emp_status_col]].copy()
        tmp[uzio_emp_status_col] = tmp[uzio_emp_status_col].map(norm_blank)
        tmp = tmp[tmp[UZIO_KEY] != ""]
        for _, r in tmp.iterrows():
            eid = str(r[UZIO_KEY]).strip()
            v = r[uzio_emp_status_col]
            if eid and norm_blank(v) != "" and eid not in uzio_status_map:
                uzio_status_map[eid] = str(v)

    paycom_status_map = {}
    if paycom_emp_status_col in paycom.columns:
        tmp = paycom[[PAYCOM_KEY, paycom_emp_status_col]].copy()
        tmp[paycom_emp_status_col] = tmp[paycom_emp_status_col].map(norm_blank)
        tmp = tmp[tmp[PAYCOM_KEY] != ""]
        for _, r in tmp.iterrows():
            eid = str(r[PAYCOM_KEY]).strip()
            v = r[paycom_emp_status_col]
            if eid and norm_blank(v) != "" and eid not in paycom_status_map:
                paycom_status_map[eid] = str(v)

    def get_emp_status(eid: str) -> str:
        eid = (eid or "").strip()
        if eid in uzio_status_map:
            return str(uzio_status_map[eid])
        if eid in paycom_status_map:
            return str(paycom_status_map[eid])
        return ""

    # pay type map (prefer UZIO)
    uzio_pay_type_col = 'Pay Type'
    paycom_pay_type_col = norm_colname(PAYCOM_FIELD_MAP.get('Pay Type', ''))

    pay_type_map = {}
    if uzio_pay_type_col in uzio.columns:
        tmp = uzio[[UZIO_KEY, uzio_pay_type_col]].copy()
        tmp[uzio_pay_type_col] = tmp[uzio_pay_type_col].map(norm_blank)
        tmp = tmp[tmp[UZIO_KEY] != ""]
        for _, r in tmp.iterrows():
            eid = str(r[UZIO_KEY]).strip()
            v = r[uzio_pay_type_col]
            if eid and norm_blank(v) != "" and eid not in pay_type_map:
                pay_type_map[eid] = canonical_pay_type(v)

    if paycom_pay_type_col in paycom.columns:
        tmp = paycom[[PAYCOM_KEY, paycom_pay_type_col]].copy()
        tmp[paycom_pay_type_col] = tmp[paycom_pay_type_col].map(norm_blank)
        tmp = tmp[tmp[PAYCOM_KEY] != ""]
        for _, r in tmp.iterrows():
            eid = str(r[PAYCOM_KEY]).strip()
            v = r[paycom_pay_type_col]
            if eid and norm_blank(v) != "" and eid not in pay_type_map:
                pay_type_map[eid] = canonical_pay_type(v)

    # index maps (keep first occurrence per employee)
    uzio_idx = {}
    for i, eid in uzio[UZIO_KEY].items():
        e = str(eid).strip()
        if e and e not in uzio_idx:
            uzio_idx[e] = i

    paycom_idx = {}
    for i, eid in paycom[PAYCOM_KEY].items():
        e = str(eid).strip()
        if e and e not in paycom_idx:
            paycom_idx[e] = i

    # ---------- FLSA Classification column (Uzio) ----------
    uzio_flsa_col = 'FLSA Classification'

    # Also locate employee name columns in Uzio for context in FLSA report
    uzio_fname_col = 'First Name'
    uzio_lname_col = 'Last Name'

    all_emps = sorted(set(uzio_idx.keys()).union(set(paycom_idx.keys())))

    rows = []
    for eid in all_emps:
        u_i = uzio_idx.get(eid)
        p_i = paycom_idx.get(eid)

        emp_status_context = get_emp_status(eid)
        emp_pay_type = pay_type_map.get(eid, "")

        for field in mapped_fields:
            uz_field = field # Internal Standard Name
            pc_col_raw = PAYCOM_FIELD_MAP.get(field)
            if not pc_col_raw:
                continue
            pc_col = norm_colname(pc_col_raw)

            uz_missing_row = (u_i is None)
            pc_missing_row = (p_i is None)

            uz_missing_col = (uz_field not in uzio.columns)
            pc_missing_col = (pc_col not in paycom.columns)

            uz_val = ""
            pc_val = ""
            if (not uz_missing_row) and (not uz_missing_col):
                uz_val = uzio.loc[u_i, uz_field]
            if (not pc_missing_row) and (not pc_missing_col):
                pc_val = paycom.loc[p_i, pc_col]

            # Decide status
            if pc_missing_row and (not uz_missing_row):
                status = "Employee ID Not Found in Paycom"
            elif uz_missing_row and (not pc_missing_row):
                status = "Employee ID Not Found in Uzio"
            elif pc_missing_col:
                status = "Column Missing in Paycom Sheet"
            elif uz_missing_col:
                status = "Column Missing in Uzio Sheet"
            else:
                # ✅ Pay-type based ignore rules (your latest requirement)
                if should_ignore_field_for_paytype(uz_field, emp_pay_type):
                    status = "Data Match"
                else:
                    same = normalized_compare(uz_field, uz_val, pc_val)
                    if same:
                        status = "Data Match"
                    else:
                        uz_b = norm_blank(uz_val)
                        pc_b = norm_blank(pc_val)
                        
                        is_terminated_context = "term" in emp_status_context.lower()
                        
                        # Apply special Employment Status missing logic matching ADP tool
                        f_case = norm_colname(uz_field).casefold()
                        if "employment status" in f_case and pc_b != "":
                            uz_stat = canonical_employment_status(uz_b)
                            pc_stat = canonical_employment_status(pc_b)
                            
                            if "term" in uz_stat and "inactive" in pc_b.lower():
                                status = "Data Match"
                            elif "active" in uz_stat:
                                status = "Active in Uzio"
                            elif "term" in uz_stat:
                                status = "Terminated in Uzio"
                            elif uz_b == "" and "active" in pc_stat:
                                status = "Active in Paycom"
                            elif uz_b == "" and ("term" in pc_stat or "retire" in pc_stat):
                                status = "Terminated in Paycom"
                            else:
                                status = "Data Mismatch"
                        else:
                            # Standard missing/mismatch logic
                            if is_terminated_context:
                                status = "Data Match"
                            elif (uz_b == "" or uz_b is None) and (pc_b != "" and pc_b is not None):
                                status = "Value missing in Uzio (Paycom has value)"
                            elif (uz_b != "" and uz_b is not None) and (pc_b == "" or pc_b is None):
                                status = "Value missing in Paycom (Uzio has value)"
                            else:
                                status = "Data Mismatch"

            rows.append(
                {
                    "Employee": display_id_map.get(eid, eid),  # Use original leading-zero form
                    "Field": uz_field,
                    "Employment Status": emp_status_context,  # extra context column
                    "UZIO_Value": uz_val,
                    "PAYCOM_Value": pc_val,
                    "PAYCOM_SourceOfTruth_Status": status,
                }
            )

    comparison_detail = pd.DataFrame(
        rows,
        columns=[
            "Employee",
            "Field",
            "Employment Status",
            "UZIO_Value",
            "PAYCOM_Value",
            "PAYCOM_SourceOfTruth_Status",
        ],
    )

    # ---------------- Salaried Driver Exceptions ----------------
    salaried_drivers_pc = []
    pc_pay_type_col = norm_colname(PAYCOM_FIELD_MAP.get('Pay Type', ''))
    pc_job_title_col = norm_colname(PAYCOM_FIELD_MAP.get('Job Title', ''))
    pc_flsa_col = norm_colname(PAYCOM_FIELD_MAP.get('FLSA Classification', ''))
    uzio_flsa_col_str = 'FLSA Classification'
    uzio_pay_type_col_str = 'Pay Type'
    uzio_emp_status_col_str = 'Employment Status'

    if pc_pay_type_col in paycom.columns and pc_job_title_col in paycom.columns:
        for idx_label, row in paycom.iterrows():
            pay_val = str(row[pc_pay_type_col]).strip().lower()
            if "salary" in pay_val or "salaried" in pay_val:
                jt_raw = row[pc_job_title_col]
                jt_val = str(jt_raw).strip().lower() if pd.notna(jt_raw) else ""
                if jt_val and jt_val != "nan":
                    if is_hourly_only_job_title(jt_val):
                        emp_id = str(row[PAYCOM_KEY]).strip()

                        # --- Paycom values ---
                        pc_pay_type_val = str(row[pc_pay_type_col]).strip()
                        pc_emp_status_val = str(paycom_status_map.get(emp_id, "Not Found")).strip()
                        pc_flsa_val = ""
                        if pc_flsa_col and pc_flsa_col in paycom.columns:
                            pc_flsa_val = str(norm_blank(row.get(pc_flsa_col, "")) or "").strip()

                        # --- Uzio values (look up via index) ---
                        uz_i = uzio_idx.get(emp_id)
                        uz_pay_type_val = ""
                        uz_emp_status_val = ""
                        uz_flsa_val = ""
                        if uz_i is not None:
                            if uzio_pay_type_col_str in uzio.columns:
                                uz_pay_type_val = str(norm_blank(uzio.loc[uz_i, uzio_pay_type_col_str]) or "").strip()
                            if uzio_emp_status_col_str in uzio.columns:
                                uz_emp_status_val = str(norm_blank(uzio.loc[uz_i, uzio_emp_status_col_str]) or "").strip()
                            if uzio_flsa_col_str in uzio.columns:
                                uz_flsa_val = str(norm_blank(uzio.loc[uz_i, uzio_flsa_col_str]) or "").strip()

                        # --- Build smart Comment ---
                        comment_parts = [
                            f"Paycom lists this employee as '{str(jt_raw).strip()}' with Pay Type '{pc_pay_type_val}'.",
                            "Uzio requires this job title to be Hourly/Non-Exempt — a Salaried assignment will cause a conflict.",
                        ]
                        if uz_emp_status_val:
                            comment_parts.append(f"Uzio status: {uz_emp_status_val}.")
                        if pc_emp_status_val and pc_emp_status_val != "Not Found":
                            comment_parts.append(f"Paycom status: {pc_emp_status_val}.")
                        if uz_flsa_val:
                            comment_parts.append(f"Uzio FLSA: {uz_flsa_val}.")
                        if pc_flsa_val:
                            comment_parts.append(f"Paycom FLSA: {pc_flsa_val}.")
                        if not uz_emp_status_val and uz_i is None:
                            comment_parts.append("Employee NOT found in Uzio — will need to be added as Hourly.")
                        comment = " ".join(comment_parts)

                        salaried_drivers_pc.append({
                            'Employee ID': emp_id,
                            'Job Title (Paycom)': str(row[pc_job_title_col]).strip(),
                            'Pay Type (Paycom)': pc_pay_type_val,
                            'Pay Type (Uzio)': uz_pay_type_val if uz_pay_type_val else "Not in Uzio",
                            'Employment Status (Paycom)': pc_emp_status_val,
                            'Employment Status (Uzio)': uz_emp_status_val if uz_emp_status_val else "Not in Uzio",
                            'FLSA Classification (Paycom)': pc_flsa_val if pc_flsa_val else "Blank",
                            'FLSA Classification (Uzio)': uz_flsa_val if uz_flsa_val else "Blank" if uz_i is not None else "Not in Uzio",
                            'Comment': comment
                        })
    df_salaried_drivers_pc = pd.DataFrame(salaried_drivers_pc)

    # ---------- FLSA Compliance Issues (4th sheet) ----------
    flsa_rows = []
    if uzio_flsa_col is not None:
        for eid, u_i in uzio_idx.items():
            # Get Pay Type from Uzio
            pay_canon = pay_type_map.get(eid, "")

            # Get FLSA Classification from Uzio
            flsa_raw = ""
            if uzio_flsa_col in uzio.columns:
                flsa_raw = uzio.loc[u_i, uzio_flsa_col]
            flsa_norm = normalize_space_and_case(flsa_raw)

            # Detect invalid combinations
            issue = ""
            if pay_canon == "hourly" and "exempt" in flsa_norm and "non" not in flsa_norm:
                issue = "Hourly employee classified as Exempt"
            elif pay_canon == "salaried" and ("non-exempt" in flsa_norm or "non exempt" in flsa_norm or "nonexempt" in flsa_norm):
                issue = "Salaried employee classified as Non-Exempt"

            if issue:
                # Get employee name for context
                fname = ""
                lname = ""
                if uzio_fname_col and uzio_fname_col in uzio.columns:
                    fname = str(norm_blank(uzio.loc[u_i, uzio_fname_col]) or "")
                if uzio_lname_col and uzio_lname_col in uzio.columns:
                    lname = str(norm_blank(uzio.loc[u_i, uzio_lname_col]) or "")
                emp_name = f"{fname} {lname}".strip()

                # Get Pay Type raw value from Uzio for display
                pay_raw = ""
                if uzio_pay_type_col and uzio_pay_type_col in uzio.columns:
                    pay_raw = str(norm_blank(uzio.loc[u_i, uzio_pay_type_col]) or "")

                flsa_rows.append({
                    "Employee ID": display_id_map.get(eid, eid),
                    "Employee Name": emp_name,
                    "Pay Type (Uzio)": pay_raw,
                    "FLSA Classification (Uzio)": str(norm_blank(flsa_raw) or ""),
                    "Issue": issue,
                })

    flsa_issues = pd.DataFrame(flsa_rows, columns=[
        "Employee ID", "Employee Name", "Pay Type (Uzio)",
        "FLSA Classification (Uzio)", "Issue"
    ])

    # ---------- Data Quality Issues (00/00/0000 dates) ----------
    dq_rows = []
    
    # Locate Emp ID and Name columns again for context
    pc_fname_col = find_col(paycom.columns, "Legal_Firstname", "Legal Firstname", "First Name", "FirstName")
    if pc_fname_col is None:
        for c in paycom.columns:
            cl = norm_colname(c).casefold()
            if "first" in cl and "name" in cl:
                pc_fname_col = c
                break
    pc_lname_col = find_col(paycom.columns, "Legal_Lastname", "Legal Lastname", "Last Name", "LastName")
    if pc_lname_col is None:
        for c in paycom.columns:
            cl = norm_colname(c).casefold()
            if "last" in cl and "name" in cl:
                pc_lname_col = c
                break

    for eid in paycom_idx.keys():
        p_i = paycom_idx.get(eid)
        if p_i is not None:
            # Check all columns for this row
            for col in paycom.columns:
                val = paycom.loc[p_i, col]
                if pd.notna(val) and '00/00/0000' in str(val):
                    fname = str(norm_blank(paycom.loc[p_i, pc_fname_col]) or "") if pc_fname_col else ""
                    lname = str(norm_blank(paycom.loc[p_i, pc_lname_col]) or "") if pc_lname_col else ""
                    emp_name = f"{fname} {lname}".strip()
                    pc_raw_id = paycom_orig_keys.loc[p_i] if p_i in paycom_orig_keys.index else eid
                    
                    dq_rows.append({
                        "Employee ID": str(pc_raw_id).strip(),
                        "Employee Name": emp_name,
                        "Column": col,
                        "Invalid Value Found": str(val)
                    })
                    
    dq_issues = pd.DataFrame(dq_rows, columns=[
        "Employee ID", "Employee Name", "Column", "Invalid Value Found"
    ])

    # ---------- Active Employees Missing in Uzio (5th sheet) ----------
    # Find employees in Paycom but NOT in Uzio who are Active / On Leave
    paycom_only_emps = set(paycom_idx.keys()) - set(uzio_idx.keys())

    # (Already located above for DQ checks, but redeclared here if needed, safe to keep as is)
    if pc_fname_col is None:
        for c in paycom.columns:
            cl = norm_colname(c).casefold()
            if "first" in cl and "name" in cl:
                pc_fname_col = c
                break
    if pc_lname_col is None:
        for c in paycom.columns:
            cl = norm_colname(c).casefold()
            if "last" in cl and "name" in cl:
                pc_lname_col = c
                break
    pc_hire_col = find_col(paycom.columns, "Most_Recent_Hire_Date", "Most Recent Hire Date",
                           "Hire_Date", "Hire Date")
    if pc_hire_col is None:
        for c in paycom.columns:
            cl = norm_colname(c).casefold()
            if "hire" in cl and "date" in cl:
                pc_hire_col = c
                break

    active_missing_rows = []
    for eid in sorted(paycom_only_emps):
        p_i = paycom_idx[eid]
        # Check employment status
        status_val = ""
        if paycom_emp_status_col and paycom_emp_status_col in paycom.columns:
            status_val = str(norm_blank(paycom.loc[p_i, paycom_emp_status_col]) or "")
        status_lower = status_val.strip().lower()

        # Only include Active / On Leave employees
        if status_lower not in {"active", "on leave", "leave", "activated"}:
            continue

        fname = ""
        lname = ""
        if pc_fname_col and pc_fname_col in paycom.columns:
            fname = str(norm_blank(paycom.loc[p_i, pc_fname_col]) or "")
        if pc_lname_col and pc_lname_col in paycom.columns:
            lname = str(norm_blank(paycom.loc[p_i, pc_lname_col]) or "")
        emp_name = f"{fname} {lname}".strip()

        hire_date = ""
        if pc_hire_col and pc_hire_col in paycom.columns:
            hire_date = str(norm_blank(paycom.loc[p_i, pc_hire_col]) or "")

        active_missing_rows.append({
            "Employee ID": display_id_map.get(eid, eid),
            "Employee Name": emp_name,
            "Employment Status (Paycom)": status_val,
            "Date of Hire (Paycom)": hire_date,
        })

    active_missing_in_uzio = pd.DataFrame(active_missing_rows, columns=[
        "Employee ID", "Employee Name",
        "Employment Status (Paycom)", "Date of Hire (Paycom)"
    ])

    # Field summary
    statuses = [
        "Data Match",
        "Data Mismatch",
        "Value missing in Uzio (Paycom has value)",
        "Value missing in Paycom (Uzio has value)",
        "Employee ID Not Found in Uzio",
        "Employee ID Not Found in Paycom",
        "Column Missing in Paycom Sheet",
        "Column Missing in Uzio Sheet",
    ]

    if not comparison_detail.empty:
        field_summary_by_status = (
            comparison_detail.pivot_table(
                index="Field",
                columns="PAYCOM_SourceOfTruth_Status",
                values="Employee",
                aggfunc="count",
                fill_value=0,
            )
            .reindex(columns=statuses, fill_value=0)
            .reset_index()
        )
        field_summary_by_status["Total"] = field_summary_by_status[statuses].sum(axis=1)
    else:
        field_summary_by_status = pd.DataFrame(columns=["Field"] + statuses + ["Total"])

    # Summary
    uzio_emps = set(uzio[UZIO_KEY].dropna().map(str))
    paycom_emps = set(paycom[PAYCOM_KEY].dropna().map(str))

    summary = pd.DataFrame(
        {
            "Metric": [
                "Total UZIO Employees",
                "Total PAYCOM Employees",
                "Employees in both",
                "Employees only in UZIO",
                "Employees only in PAYCOM",
                "Total UZIO Records",
                "Total PAYCOM Records",
                "Fields Compared",
                "Total Comparisons (field-level rows)",
                "FLSA Compliance Issues",
                "Active in Paycom but Missing in Uzio",
                "Salaried Driver Exceptions",
            ],
            "Value": [
                len(uzio_emps),
                len(paycom_emps),
                len(uzio_emps & paycom_emps),
                len(uzio_emps - paycom_emps),
                len(paycom_emps - uzio_emps),
                int(len(uzio)),
                int(len(paycom)),
                int(len(PAYCOM_FIELD_MAP)),
                int(comparison_detail.shape[0]),
                len(flsa_rows),
                len(active_missing_rows),
                len(df_salaried_drivers_pc),
            ],
        }
    )

    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        field_summary_by_status.to_excel(writer, sheet_name="Field_Summary_By_Status", index=False)
        comparison_detail.to_excel(writer, sheet_name="Comparison_Detail_AllFields", index=False)
        flsa_issues.to_excel(writer, sheet_name="FLSA_Compliance_Issues", index=False)
        dq_issues.to_excel(writer, sheet_name="Data_Quality_Issues", index=False)
        active_missing_in_uzio.to_excel(writer, sheet_name="Active_Missing_In_Uzio", index=False)
        if not df_salaried_drivers_pc.empty:
            df_salaried_drivers_pc.to_excel(writer, sheet_name="Salaried_Driver_Exceptions", index=False)

    return out.getvalue()

# ---------- UI ----------
def render_ui():
    st.title(APP_TITLE)
    st.markdown("""
    **Instructions**:
    1. Upload **Uzio Census Export** (.xlsm).
    2. Upload **Paycom Census Export** (.csv or .xlsx).
    
    **Output Reports**:
    - **Comparison**: Discrepancies between Uzio and Paycom.
    - **FLSA_Compliance_Issues**: Flags employees where 'FLSA Status' does not match their assigned 'Pay Type' constraints.
    - **Active_Missing_In_Uzio**: Active employees found in Paycom but genuinely missing from the Uzio census entirely.
    - **Data_Quality_Issues**: Identifies unexpected placeholder dates such as '00/00/0000'.
    - **Salaried_Driver_Exceptions**: Employees mapped as salaried drivers, which are incompatible.
    """)

    uzio_file = st.file_uploader("Upload Uzio Census Export (.xlsm)", type=["xlsm"])
    paycom_file = st.file_uploader("Upload Paycom Census Export (.csv or .xlsx)", type=["csv", "xlsx"])
    
    client_name = st.text_input("Client Name", value="Client", key="paycom_census_client")

    if st.button("Run Audit", type="primary", disabled=(not uzio_file or not paycom_file)):
        try:
            with st.spinner("Running audit..."):
                out_excel = run_comparison(uzio_file, paycom_file)
            st.success("Audit Complete!")
            timestamp = pd.Timestamp.now().strftime('%d_%m_%Y_%H%M')
            filename = f"{client_name}_Uzio_Paycom_Census_Audit_Report_{timestamp}.xlsx"

            st.download_button(
                label="Download Audit Report",
                data=out_excel,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        except Exception as e:
            st.error(f"Error during audit: {e}")
            # Add error logging logic here if requested
            print(f"ERROR: {e}")

if __name__ == "__main__":
    st.set_page_config(page_title=APP_TITLE, layout="centered", initial_sidebar_state="collapsed")
    render_ui()
