# app.py
import io
import re
from datetime import datetime, date

import numpy as np
import pandas as pd
import streamlit as st

# =========================================================
# UZIO vs ADP – Payment & Emergency Contact Comparison Tool
#
# INPUT workbook tabs:
#   - Uzio Data
#   - ADP Payment Data
#   - ADP Emergency Contact Data
#   - Payment_Mapping
#   - Emergency_Mapping
#
# OUTPUT (two independent reports):
#   - Summary
#   - Field_Summary_By_Status
#       (columns removed: MISSING_IN_ADP, ADP_COLUMN_MISSING, UZIO_COLUMN_MISSING)
#   - Comparison_Detail_AllFields
#       (NO FieldKey column)
#
# FIXES / RULES INCLUDED:
# 1) Phone normalization: (410) 292-5939 == 4102925939
# 2) Name normalization: "Bell, Ronald" == "Ronald Bell"
#    Compares FIRST + LAST only (ignores middle names)
# 3) Paycheck Distribution normalization:
#    UZIO "Flat Dollar" treated as "amount"
# 4) UZIO FULL-row inference:
#    If employee has multiple payment rows and exactly one row has BOTH
#    Paycheck Amount blank AND Paycheck Percentage blank,
#    treat it as FULL/remainder:
#      - set Paycheck Distribution to "Percentage"
#      - set Paycheck Percentage to 100 - sum(other partial% if any), else 100
# 5) ADP payment business rule normalization:
#    - FULL => percentage + 100 (or remainder when Partial% exists)
#    - Partial => amount
#    - Partial% => percentage
#    - Full + Partial => Full is last priority (Partial accounts before it)
#    - Full + Partial% => Full% = 100 - sum(Partial%); Full last priority
# 6) Remove sheets from output:
#    - Mismatches_Only (not created)
#    - Mapping_ADP_Col_Missing (not created)
# =========================================================

APP_TITLE = "UZIO vs ADP – Payment & Emergency Contact Comparison Tool"

UZIO_SHEET = "Uzio Data"
ADP_PAY_SHEET = "ADP Payment Data"
ADP_EC_SHEET = "ADP Emergency Contact Data"
PAY_MAP_SHEET = "Payment_Mapping"
EC_MAP_SHEET = "Emergency_Mapping"

# ---------- Helpers ----------
# ---------- Helpers ----------
def norm_colname(c: str) -> str:
    """
    Normalize column names to a standard format for easier matching.
    - Replaces newlines and non-breaking spaces with standard spaces.
    - Standardizes quotes (single and double).
    - Removes extra whitespace and asterisks.
    """
    if c is None:
        return ""
    c = str(c).replace("\n", " ").replace("\r", " ")
    c = c.replace("\u00A0", " ")
    c = c.replace("’", "'").replace("“", '"').replace("”", '"')
    c = re.sub(r"\s+", " ", c).strip()
    c = c.replace("*", "")
    c = c.strip('"').strip("'")
    return c


def norm_blank(x):
    """
    Normalize blank values (None, NaN, empty strings, 'null', 'nan') to an empty string.
    This ensures consistent handling of missing data.
    """
    if x is None:
        return ""
    if isinstance(x, float) and np.isnan(x):
        return ""
    if isinstance(x, str) and x.strip().lower() in {"", "nan", "none", "null"}:
        return ""
    return x


def digits_only(x):
    """Extract digits while handling numeric types safely (avoid '.0' artifacts)."""
    x = norm_blank(x)
    if x == "":
        return ""
    try:
        if isinstance(x, (int, np.integer)):
            return str(int(x))
        if isinstance(x, (float, np.floating)):
            if float(x).is_integer():
                return str(int(x))
    except Exception:
        pass

    s = str(x).strip()
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".")[0]
    return re.sub(r"\D", "", s)


def digits_only_padded(x, width: int):
    d = digits_only(x)
    if d == "":
        return ""
    if len(d) < width:
        d = d.zfill(width)
    return d


def try_parse_date(x):
    x = norm_blank(x)
    if x == "":
        return ""
    if isinstance(x, (datetime, date, np.datetime64, pd.Timestamp)):
        return pd.to_datetime(x).date().isoformat()
    if isinstance(x, str):
        s = x.strip()
        try:
            return pd.to_datetime(s, errors="raise").date().isoformat()
        except Exception:
            return s
    return str(x)


NUMERIC_KEYWORDS = {"salary", "rate", "hours", "amount", "percent", "percentage", "priority"}
DATE_KEYWORDS = {"date", "dob", "birth", "effective"}
ZIP_KEYWORDS = {"zip", "zipcode", "postal"}
PHONE_KEYWORDS = {"phone", "mobile"}
NAME_KEYWORDS = {"name"}
DISTRIBUTION_KEYWORDS = {"distribution", "deposit type"}

ROUTING_KEYWORDS = {"routing"}
ACCOUNTNUM_KEYWORDS = {"account number"}


def norm_phone_digits(x):
    """Normalize phone numbers so (410) 292-5939 == 4102925939."""
    d = digits_only(x)
    if d == "":
        return ""
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    if len(d) > 10:
        d = d[-10:]
    return d


def norm_zip_first5(x):
    x = norm_blank(x)
    if x == "":
        return ""
    if isinstance(x, (int, np.integer)):
        s = str(int(x))
    elif isinstance(x, (float, np.floating)) and float(x).is_integer():
        s = str(int(x))
    else:
        s = re.sub(r"[^\d]", "", str(x).strip())
    if s == "":
        return ""
    if 0 < len(s) < 5:
        s = s.zfill(5)
    return s[:5]


def normalize_person_name(x: str) -> str:
    """
    Normalize person names so these match:
      - "Bell, Ronald" == "Ronald Bell"
      - "Young, Roscoe Robert" == "Roscoe Young" (middle ignored)
    Compare FIRST + LAST only.
    """
    s = norm_blank(x)
    if s == "":
        return ""
    s = str(s).strip().replace("\u00A0", " ")

    def _clean_tokens(txt: str):
        txt = re.sub(r"[^A-Za-z0-9\s]", " ", txt)
        txt = re.sub(r"\s+", " ", txt).strip()
        return [t for t in txt.split(" ") if t]

    if "," in s:
        parts = [p.strip() for p in s.split(",") if p.strip()]
        last_part = parts[0] if len(parts) >= 1 else ""
        first_part = parts[1] if len(parts) >= 2 else ""
        last_tokens = _clean_tokens(last_part)
        first_tokens = _clean_tokens(first_part)

        first = first_tokens[0] if first_tokens else ""
        last_name = last_tokens[-1] if last_tokens else ""

        if first and last_name:
            return f"{first} {last_name}".casefold()
        return (first or last_name).casefold()

    toks = _clean_tokens(s)
    if not toks:
        return ""
    if len(toks) == 1:
        return toks[0].casefold()
    first = toks[0]
    last_name = toks[-1]
    return f"{first} {last_name}".casefold()


def norm_distribution_token(val: str) -> str:
    """
    Normalize Paycheck Distribution / Deposit Type variants to two tokens:
      - 'amount'
      - 'percentage'
    """
    v = norm_blank(val)
    if v == "":
        return ""
    s = str(v).strip().casefold()

    # UZIO variants for amount
    if "flat dollar" in s or "flat amount" in s or ("flat" in s and "dollar" in s):
        return "amount"
    if "dollar" in s and ("flat" in s or "amount" in s):
        return "amount"

    # Generic UZIO variants
    if "amount" in s:
        return "amount"
    if "%" in s or "percent" in s or "percentage" in s or "age" in s:
        return "percentage"

    # ADP variants
    if ("partial" in s and "%" in s) or "partial%" in s:
        return "percentage"
    if "partial" in s:
        return "amount"
    if "full" in s:
        return "percentage"

    return re.sub(r"\s+", " ", s).strip()


def norm_account_type(x: str) -> str:
    """
    Normalize Account Type to handle ADP codes:
      - 'CK1 - checking' -> 'checking'
      - 'SV1 - savings' -> 'savings'
      - 'Checking' -> 'checking'
    """
    s = str(norm_blank(x)).strip().casefold()
    if s == "":
        return ""
    # Strip prefix like "ck1 - " or "sv2 - "
    # Regex look for: start, optional alphanumeric, optional space, hyphen, space, then capture rest
    m = re.match(r"^(?:ck|sv)\d*\s*[-–]\s*(.*)", s)
    if m:
        return m.group(1).strip()
    return s



def norm_value(x, field_name: str):
    """
    Master normalization function that applies specific rules based on the field name.
    - Phones: digits only, last 10 digits
    - Zips: first 5 digits
    - Dates: standard YYYY-MM-DD
    - Names: First Last (ignore middle)
    - Accounts: Remove special chars
    """
    f = norm_colname(field_name).casefold()
    x = norm_blank(x)
    if x == "":
        return ""

    if any(k in f for k in PHONE_KEYWORDS):
        return norm_phone_digits(x)

    if any(k in f for k in ZIP_KEYWORDS):
        return norm_zip_first5(x)

    if any(k in f for k in ROUTING_KEYWORDS):
        return digits_only_padded(x, 9)

    if any(k in f for k in ACCOUNTNUM_KEYWORDS):
        return digits_only(x)

    if any(k in f for k in DATE_KEYWORDS):
        return try_parse_date(x)

    if any(k in f for k in NAME_KEYWORDS):
        return normalize_person_name(x)

    if any(k in f for k in DISTRIBUTION_KEYWORDS):
        return norm_distribution_token(x)

    # Added: Account Type specific normalization
    if "account" in f and "type" in f:
        return norm_account_type(x)

    if any(k in f for k in NUMERIC_KEYWORDS):
        # Added: Percentage handling (strip % and parse as is, do not div by 100)
        s_raw = str(x).strip()
        if "%" in s_raw:
            s_clean = s_raw.replace("%", "").strip()
            try:
                return float(s_clean)
            except:
                pass

        if isinstance(x, (int, float, np.integer, np.floating)):
            return float(x)
        if isinstance(x, str):
            s = x.strip().replace(",", "").replace("$", "")
            try:
                return float(s)
            except Exception:
                return re.sub(r"\s+", " ", x.strip()).casefold()

    if isinstance(x, str):
        return re.sub(r"\s+", " ", x.strip()).casefold()

    return str(x).casefold()


def is_fuzzy_match(v1, v2) -> bool:
    """
    Compare two values allowing for:
    1. Exact equality
    2. Float tolerance (e.g. 99.8 vs 99.80001)
    3. Percentage scaling (e.g. 20 vs 0.2, or 0.03 vs 3)
    """
    if v1 == v2:
        return True
    if v1 == "" or v2 == "":
        return False
    
    # Try float comparison
    try:
        f1 = float(v1)
        f2 = float(v2)
        
        # Tolerance check
        if abs(f1 - f2) < 0.01:
            return True
        
        # Scaling check (x100)
        # Check if f1 is approx f2 * 100
        if abs(f1 - (f2 * 100.0)) < 0.01:
            return True
        # Check if f2 is approx f1 * 100
        if abs(f2 - (f1 * 100.0)) < 0.01:
            return True
            
    except:
        pass
        
    return False



def norm_key_series(s: pd.Series) -> pd.Series:
    s2 = s.astype(object).where(~s.isna(), "")
    def _fix(v):
        v = str(v).strip()
        v = v.replace("\u00A0", " ")
        if re.fullmatch(r"\d+\.0+", v):
            v = v.split(".")[0]
        return v
    return s2.map(_fix)


def find_col(df_cols, *candidate_names):
    """
    Search for a column name in a dataframe given a list of candidate names.
    Returns the actual column name if found, else None.
    """
    norm_map = {norm_colname(c).casefold(): c for c in df_cols}
    for cand in candidate_names:
        key = norm_colname(cand).casefold()
        if key in norm_map:
            return norm_map[key]
    return None


def resolve_adp_col_label(label: str, adp_cols_all) -> str:
    """
    Resolve mapping sheet labels to actual ADP columns when possible.
    If cannot resolve, keep it as a constant: __CONST__:<label>
    """
    if label is None:
        return ""
    raw = str(label).strip()
    raw = raw.replace("’", "'").replace("“", '"').replace("”", '"')
    raw = raw.strip().strip(",")
    if raw == "":
        return ""

    adp_norm = {norm_colname(c).casefold(): c for c in adp_cols_all}

    direct = norm_colname(raw).casefold()
    if direct in adp_norm:
        return adp_norm[direct]

    # If mapping has patterns like: ASSOCIATE ID (or "Associate ID")
    parts = re.split(r"\(|\)|\bor\b|/|,|;", raw, flags=re.IGNORECASE)
    parts = [norm_colname(p) for p in parts if norm_colname(p)]

    # Also split patterns like "SV1 - savings"
    extra = []
    for p in parts:
        extra.extend([norm_colname(x) for x in re.split(r"\s[-–]\s", p) if norm_colname(x)])
    parts = parts + extra

    # Try exact matches for each part
    for p in parts:
        k = norm_colname(p).casefold()
        if k in adp_norm:
            return adp_norm[k]

    # Try contains match
    for k_norm, actual in adp_norm.items():
        if k_norm and (k_norm in direct or direct in k_norm):
            return actual

    # Otherwise treat as constant
    return f"__CONST__:{raw}"



# ---------- Numeric helpers ----------
def _safe_float(x):
    x = norm_blank(x)
    if x == "":
        return np.nan
    try:
        if isinstance(x, (int, float, np.integer, np.floating)):
            return float(x)
        s = str(x).strip().replace(",", "").replace("$", "")
        return float(s)
    except Exception:
        return np.nan


def _is_blank_money_or_percent(v) -> bool:
    s = str(norm_blank(v)).strip()
    if s == "":
        return True
    s2 = s.replace("$", "").replace(",", "").replace("%", "").strip()
    return s2 == ""


def _safe_percentage(x):
    """
    Parse percentage value, handling:
    - '20%' -> 20.0
    - 0.2 -> 20.0 (if <= 1.0, scale up)
    """
    x = norm_blank(x)
    if x == "":
        return np.nan
    try:
        # Handle string with %
        if isinstance(x, str):
            s = x.strip().replace(",", "").replace("$", "")
            if "%" in s:
                s = s.replace("%", "")
                return float(s)
            
            # If string without %, parse float
            f = float(s)
            # Scaling check for string inputs? 
            # E.g. "0.2" -> 20? 
            # Safer to assume if user types "0.2" they might mean 0.2%, 
            # BUT consistent with Excel logic, let's treat <= 1.0 as x100
            if 0 < abs(f) <= 1.0:
                 return f * 100.0
            return f

        if isinstance(x, (int, float, np.integer, np.floating)):
            f = float(x)
            # Assumption: If percentage is <= 1.0 (e.g., 0.2), treat it as 20%.
            # This handles Excel formatting where 20% is stored as 0.2.
            if 0 < abs(f) <= 1.0:
                return f * 100.0
            return f
            
        return np.nan
    except Exception:
        return np.nan



# ---------- Payment normalization (business rule) ----------
def normalize_adp_payment_table(adp_pay: pd.DataFrame, emp_col: str) -> pd.DataFrame:
    """
    Adds UZIO-like derived columns to ADP payment DF:
      - Paycheck Distribution (amount/percentage)
      - Paycheck Percentage
      - Paycheck Amount
      - Priority (recomputed so FULL is last when mixed)
      - Payment Method (constant 'Direct Deposit')
    """
    df = adp_pay.copy()

    dep_type_col = find_col(df.columns, "DEPOSIT TYPE", "Deposit Type")
    dep_pct_col = find_col(df.columns, "DEPOSIT PERCENT", "Deposit Percent", "DEPOSIT PERCENTAGE", "Deposit Percentage")
    dep_amt_col = find_col(df.columns, "DEPOSIT AMOUNT", "Deposit Amount")
    prio_col = find_col(df.columns, "PRIORITY #", "Priority #", "PRIORITY")

    df["Payment Method"] = "Direct Deposit"
    df["Paycheck Distribution"] = ""
    df["Paycheck Percentage"] = ""
    df["Paycheck Amount"] = ""
    df["Priority"] = ""

    if dep_type_col is None:
        return df

    df["_row_ord"] = np.arange(len(df))

    for emp, g in df.groupby(emp_col, sort=False):
        idxs = list(g.index)

        cats = []
        orig_prios = []
        for i in idxs:
            dt = str(norm_blank(df.at[i, dep_type_col])).strip().casefold()
            if ("partial" in dt and "%" in dt) or "partial%" in dt:
                cat = "partial_pct"
            elif "partial" in dt:
                cat = "partial_amt"
            elif "full" in dt:
                cat = "full"
            else:
                cat = "other"
            cats.append(cat)

            p = np.nan
            if prio_col is not None:
                p = _safe_float(df.at[i, prio_col])
            orig_prios.append(p)

        has_partial_pct = any(c == "partial_pct" for c in cats)
        sum_partial_pct = 0.0
        if has_partial_pct and dep_pct_col is not None:
            for i, c in zip(idxs, cats):
                if c == "partial_pct":
                    v = _safe_percentage(df.at[i, dep_pct_col])
                    if not np.isnan(v):
                        sum_partial_pct += v
        full_pct = max(0.0, 100.0 - sum_partial_pct) if has_partial_pct else 100.0

        for i, c in zip(idxs, cats):
            if c == "partial_amt":
                df.at[i, "Paycheck Distribution"] = "amount"
                df.at[i, "Paycheck Amount"] = df.at[i, dep_amt_col] if dep_amt_col is not None else ""
                df.at[i, "Paycheck Percentage"] = ""
            elif c == "partial_pct":
                df.at[i, "Paycheck Distribution"] = "percentage"
                # Use cleaned percentage for stored value too
                val = _safe_percentage(df.at[i, dep_pct_col])
                df.at[i, "Paycheck Percentage"] = val if not np.isnan(val) else ""
                df.at[i, "Paycheck Amount"] = ""
            elif c == "full":
                df.at[i, "Paycheck Distribution"] = "percentage"
                df.at[i, "Paycheck Percentage"] = full_pct
                df.at[i, "Paycheck Amount"] = ""
            else:
                pct = df.at[i, dep_pct_col] if dep_pct_col is not None else ""
                amt = df.at[i, dep_amt_col] if dep_amt_col is not None else ""
                if norm_blank(pct) != "":
                    df.at[i, "Paycheck Distribution"] = "percentage"
                    val = _safe_percentage(pct)
                    df.at[i, "Paycheck Percentage"] = val if not np.isnan(val) else pct

                    df.at[i, "Paycheck Amount"] = ""
                elif norm_blank(amt) != "":
                    df.at[i, "Paycheck Distribution"] = "amount"
                    df.at[i, "Paycheck Amount"] = amt
                    df.at[i, "Paycheck Percentage"] = ""
                else:
                    df.at[i, "Paycheck Distribution"] = ""
                    df.at[i, "Paycheck Amount"] = ""
                    df.at[i, "Paycheck Percentage"] = ""

        # Recompute priorities based on business rules:
        # 1. Partial Amount (processed first)
        # 2. Partial Percentage
        # 3. Full / Remainder (processed last)
        # 4. Other
        def _sort_key(i, orig_p):
            pkey = orig_p if not np.isnan(orig_p) else 1e18
            return (pkey, int(df.at[i, "_row_ord"]))

        ordered = []
        for cat_name in ["partial_amt", "partial_pct", "full", "other"]:
            bucket = [(i, op) for i, cat, op in zip(idxs, cats, orig_prios) if cat == cat_name]
            bucket_sorted = sorted(bucket, key=lambda t: _sort_key(t[0], t[1]))
            ordered.extend([t[0] for t in bucket_sorted])

        for new_p, i in enumerate(ordered, start=1):
            df.at[i, "Priority"] = new_p

    df.drop(columns=["_row_ord"], inplace=True, errors="ignore")
    return df


def normalize_uzio_payment_full_inference(uzio_pay: pd.DataFrame, emp_col: str) -> pd.DataFrame:
    """
    If employee has multiple payment rows and exactly one row has BOTH
    Paycheck Amount blank AND Paycheck Percentage blank:
      - treat it as FULL/remainder row
      - set Paycheck Distribution to 'Percentage'
      - set Paycheck Percentage = 100 - sum(other partial% rows) (else 100)
    """
    df = uzio_pay.copy()

    dist_col = find_col(df.columns, "Paycheck Distribution", "Deposit Type")
    pct_col = find_col(df.columns, "Paycheck Percentage", "Deposit Percent")
    amt_col = find_col(df.columns, "Paycheck Amount", "Deposit Amount")

    if dist_col is None or pct_col is None or amt_col is None:
        return df

    for emp, g in df.groupby(emp_col, sort=False):
        if len(g) < 2:
            continue

        candidate_idxs = []
        for i in g.index:
            if _is_blank_money_or_percent(df.at[i, amt_col]) and _is_blank_money_or_percent(df.at[i, pct_col]):
                candidate_idxs.append(i)

        if len(candidate_idxs) != 1:
            continue

        full_idx = candidate_idxs[0]

        sum_partial_pct = 0.0
        for i in g.index:
            if i == full_idx:
                continue
            v = _safe_float(df.at[i, pct_col])
            if not np.isnan(v):
                sum_partial_pct += v

        full_pct = max(0.0, 100.0 - sum_partial_pct) if sum_partial_pct > 0 else 100.0

        df.at[full_idx, dist_col] = "Percentage"
        df.at[full_idx, pct_col] = full_pct

    return df


def normalize_uzio_payment_priority(uzio_pay: pd.DataFrame, emp_col: str) -> pd.DataFrame:
    """
    Infers Priority for Uzio records:
      - If Priority is blank AND employee has exactly 1 row -> set Priority = 1
    """
    df = uzio_pay.copy()
    prio_col = find_col(df.columns, "Priority", "Priority #")
    
    # If column doesn't exist, create it
    if prio_col is None:
        prio_col = "Priority"
        df[prio_col] = ""
    
    # Ensure it's treated as string/object to mix int/str if needed
    df[prio_col] = df[prio_col].astype(object)

    for emp, g in df.groupby(emp_col, sort=False):
        # Case: Single row
        if len(g) == 1:
            curr_val = norm_blank(df.at[g.index[0], prio_col])
            if curr_val == "":
                df.at[g.index[0], prio_col] = 1
    
    return df



# ---------- Record key builders ----------
def build_payment_base_key(df: pd.DataFrame, emp_col: str):
    routing_col = find_col(df.columns, "ROUTING NUMBER", "Routing Number")
    acct_col = find_col(df.columns, "ACCOUNT NUMBER", "Account Number")
    dep_type_col = find_col(df.columns, "DEPOSIT TYPE", "Deposit Type")
    dep_amt_col = find_col(df.columns, "DEPOSIT AMOUNT", "Deposit Amount")
    dep_pct_col = find_col(df.columns, "DEPOSIT PERCENT", "Deposit Percent", "DEPOSIT PERCENTAGE", "Deposit Percentage")

    def _row_key(r):
        emp = norm_key_series(pd.Series([r.get(emp_col, "")])).iloc[0]
        routing = digits_only_padded(r.get(routing_col, ""), 9) if routing_col else ""
        acct = digits_only(r.get(acct_col, "")) if acct_col else ""

        dep_type = norm_value(r.get(dep_type_col, ""), "Deposit Type") if dep_type_col else ""
        amt = norm_value(r.get(dep_amt_col, ""), "Deposit Amount") if dep_amt_col else ""
        pct = norm_value(r.get(dep_pct_col, ""), "Deposit Percent") if dep_pct_col else ""

        if routing != "" or acct != "":
            return f"{emp}|BANK|{routing}|{acct}"
        return f"{emp}|NOBANK|{dep_type}|{amt}|{pct}"

    return df.apply(_row_key, axis=1)


def build_contact_base_key(df: pd.DataFrame, emp_col: str):
    """
    Constructs a unique key for comparing Emergency Contact records.
    Key format: <EmployeeID>|<NormalizedName>|<PhoneLast10>|<NormalizedRelationship>
    This key allows matching contacts even if they are listed in different orders.
    """
    name_col = find_col(df.columns, "Contact Name", "NAME", "Name")
    phone_col = find_col(df.columns, "Mobile Phone", "Phone", "MOBILE PHONE")
    rel_col = find_col(df.columns, "Relationship Description", "Relationship")

    def _row_key(r):
        emp = norm_key_series(pd.Series([r.get(emp_col, "")])).iloc[0]
        nm = normalize_person_name(r.get(name_col, "")) if name_col else ""
        ph = norm_phone_digits(r.get(phone_col, "")) if phone_col else ""
        rl = norm_value(r.get(rel_col, ""), "Relationship Description") if rel_col else ""
        return f"{emp}|{nm}|{ph}|{rl}"

    return df.apply(_row_key, axis=1)


def filter_section_rows(uzio_df: pd.DataFrame, section: str):
    """UZIO sheet may contain both sections; infer by which fields are populated."""
    if section == "Payment":
        routing = find_col(uzio_df.columns, "Routing Number", "ROUTING NUMBER")
        acct = find_col(uzio_df.columns, "Account Number", "ACCOUNT NUMBER")
        dep = find_col(uzio_df.columns, "Paycheck Distribution", "Deposit Type")
        pct = find_col(uzio_df.columns, "Paycheck Percentage", "Deposit Percent")
        amt = find_col(uzio_df.columns, "Paycheck Amount", "Deposit Amount")
        cols = [c for c in [routing, acct, dep, pct, amt] if c]
    else:
        name = find_col(uzio_df.columns, "Name", "Contact Name")
        rel = find_col(uzio_df.columns, "Relationship", "Relationship Description")
        ph = find_col(uzio_df.columns, "Phone", "Mobile Phone")
        cols = [c for c in [name, rel, ph] if c]

    if not cols:
        return uzio_df.iloc[0:0].copy()

    mask = False
    for c in cols:
        mask = mask | (uzio_df[c].map(norm_blank) != "")
    return uzio_df[mask].copy()


def group_indices(df: pd.DataFrame):
    g = {}
    for idx, k in df["_base_key"].items():
        k2 = "" if norm_blank(k) == "" else str(k)
        g.setdefault(k2, []).append(idx)
    return g


def read_mapping_sheet(xls: pd.ExcelFile, sheet_name: str, adp_all_cols: list) -> pd.DataFrame:
    m = pd.read_excel(xls, sheet_name=sheet_name, dtype=object)
    m.columns = [norm_colname(c) for c in m.columns]

    uz_col_name = None
    adp_col_name = None
    for c in m.columns:
        if norm_colname(c).casefold() in {"uzio coloumn", "uzio column"}:
            uz_col_name = c
        if norm_colname(c).casefold() in {"adp coloumn", "adp column"}:
            adp_col_name = c
    if uz_col_name is None or adp_col_name is None:
        raise ValueError(f"'{sheet_name}' must contain columns: 'UZIO Column' and 'ADP Column'.")

    m[uz_col_name] = m[uz_col_name].map(norm_colname)
    m[adp_col_name] = m[adp_col_name].map(norm_colname)

    m = m.dropna(subset=[uz_col_name, adp_col_name]).copy()
    m = m[(m[uz_col_name] != "") & (m[adp_col_name] != "")]
    m = m.drop_duplicates(subset=[uz_col_name], keep="first").copy()

    m["UZIO_Column"] = m[uz_col_name]
    m["ADP_Label"] = m[adp_col_name]
    m["ADP_Resolved_Column"] = m["ADP_Label"].map(lambda x: resolve_adp_col_label(x, adp_all_cols))

    # exclude Employee ID row from comparisons (it is only key)
    m["_uz_norm"] = m["UZIO_Column"].map(lambda x: norm_colname(x).casefold())
    m = m[m["_uz_norm"] != "employee id"].copy()
    m.drop(columns=["_uz_norm"], inplace=True)

    return m


# ---------- Field Summary cleanup ----------
def drop_unwanted_field_summary_columns(field_summary_df: pd.DataFrame) -> pd.DataFrame:
    if field_summary_df is None or field_summary_df.empty:
        return field_summary_df
    # Updated to new status names
    cols_to_drop = ["Employee ID Not Found in ADP", "Column Missing in ADP Sheet", "Column Missing in Uzio Sheet"]
    existing = [c for c in cols_to_drop if c in field_summary_df.columns]
    if existing:
        field_summary_df = field_summary_df.drop(columns=existing)
    return field_summary_df


# ---------- Core comparison ----------
def run_comparison(file_bytes: bytes) -> dict:
    xls = pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl")

    uzio = pd.read_excel(xls, sheet_name=UZIO_SHEET, dtype=str)
    adp_pay_raw = pd.read_excel(xls, sheet_name=ADP_PAY_SHEET, dtype=str)
    adp_ec = pd.read_excel(xls, sheet_name=ADP_EC_SHEET, dtype=str)

    uzio.columns = [norm_colname(c) for c in uzio.columns]
    adp_pay_raw.columns = [norm_colname(c) for c in adp_pay_raw.columns]
    adp_ec.columns = [norm_colname(c) for c in adp_ec.columns]

    UZIO_KEY = find_col(uzio.columns, "Employee ID", "EmployeeID", "Employee Id")
    if UZIO_KEY is None:
        raise ValueError("UZIO key column 'Employee ID' not found in 'Uzio Data' tab.")

    ADP_PAY_KEY = find_col(adp_pay_raw.columns, "ASSOCIATE ID", "Associate ID")
    ADP_EC_KEY = find_col(adp_ec.columns, "ASSOCIATE ID", "Associate ID")
    if ADP_PAY_KEY is None:
        raise ValueError("ADP Payment Data must contain 'ASSOCIATE ID' (or 'Associate ID').")
    if ADP_EC_KEY is None:
        raise ValueError("ADP Emergency Contact Data must contain 'ASSOCIATE ID' (or 'Associate ID').")

    uzio[UZIO_KEY] = norm_key_series(uzio[UZIO_KEY])
    adp_pay_raw[ADP_PAY_KEY] = norm_key_series(adp_pay_raw[ADP_PAY_KEY])
    adp_ec[ADP_EC_KEY] = norm_key_series(adp_ec[ADP_EC_KEY])

    adp_all_cols = list(adp_pay_raw.columns) + list(adp_ec.columns)
    pay_map = read_mapping_sheet(xls, PAY_MAP_SHEET, adp_all_cols)
    ec_map = read_mapping_sheet(xls, EC_MAP_SHEET, adp_all_cols)

    payment_derived_fields = {
        "Paycheck Distribution",
        "Paycheck Percentage",
        "Paycheck Amount",
        "Priority",
        "Payment Method",
    }
    pay_map.loc[pay_map["UZIO_Column"].isin(payment_derived_fields), "ADP_Resolved_Column"] = pay_map.loc[
        pay_map["UZIO_Column"].isin(payment_derived_fields), "UZIO_Column"
    ]

    adp_pay = normalize_adp_payment_table(adp_pay_raw, ADP_PAY_KEY)

    uzio_pay = filter_section_rows(uzio, "Payment")
    uzio_ec = filter_section_rows(uzio, "Emergency Contact")

    if len(uzio_pay):
        uzio_pay = normalize_uzio_payment_full_inference(uzio_pay, UZIO_KEY)
        uzio_pay = normalize_uzio_payment_priority(uzio_pay, UZIO_KEY)

    uzio_pay["_base_key"] = build_payment_base_key(uzio_pay, UZIO_KEY) if len(uzio_pay) else pd.Series(dtype=str)
    adp_pay["_base_key"] = build_payment_base_key(adp_pay, ADP_PAY_KEY)

    uzio_ec["_base_key"] = build_contact_base_key(uzio_ec, UZIO_KEY) if len(uzio_ec) else pd.Series(dtype=str)
    adp_ec["_base_key"] = build_contact_base_key(adp_ec, ADP_EC_KEY)

    g_uz_pay = group_indices(uzio_pay) if len(uzio_pay) else {}
    g_ad_pay = group_indices(adp_pay)
    g_uz_ec = group_indices(uzio_ec) if len(uzio_ec) else {}
    g_uz_ec = group_indices(uzio_ec) if len(uzio_ec) else {}
    g_ad_ec = group_indices(adp_ec)

    def build_report_for_section(
        section: str,
        uz_df: pd.DataFrame,
        ad_df: pd.DataFrame,
        g_uz: dict,
        g_ad: dict,
        emp_key_uz: str,
        emp_key_ad: str,
        mapping_df: pd.DataFrame,
    ) -> bytes:
        """
        Generates the comparison report for a specific section (Payment or Emergency Contact).
        - Iterates through all unique record keys (union of UZIO and ADP keys).
        - Aligns records based on the generated keys.
        - Compares fields defined in the Mapping Sheet.
        - Determines status: Data Match, Mismatch, Missing in UZIO/ADP, etc.
        """

        sec_map = mapping_df.copy()
        sec_map = sec_map[sec_map["ADP_Resolved_Column"].map(norm_blank) != ""].copy()

        base_keys = sorted(set(g_uz.keys()).union(g_ad.keys()) - {""})

        rows = []
        for bk in base_keys:
            uz_list = g_uz.get(bk, [])
            ad_list = g_ad.get(bk, [])
            pairs = max(len(uz_list), len(ad_list))

            for i in range(pairs):
                uz_idx = uz_list[i] if i < len(uz_list) else None
                ad_idx = ad_list[i] if i < len(ad_list) else None

                employee_id_out = ""
                try:
                    if uz_idx is not None and emp_key_uz in uz_df.columns:
                        v = uz_df.loc[uz_idx, emp_key_uz]
                        employee_id_out = "" if v is None else str(v)
                    elif ad_idx is not None and emp_key_ad in ad_df.columns:
                        v = ad_df.loc[ad_idx, emp_key_ad]
                        employee_id_out = "" if v is None else str(v)
                except Exception:
                    employee_id_out = ""

                employee_id_out = employee_id_out.strip()
                if employee_id_out == "":
                    try:
                        employee_id_out = str(bk).split("|")[0]
                    except Exception:
                        employee_id_out = str(bk)

                for _, r in sec_map.iterrows():
                    uz_field = r["UZIO_Column"]
                    adp_col_resolved = r["ADP_Resolved_Column"]

                    uz_val = uz_df.loc[uz_idx, uz_field] if (uz_idx is not None and uz_field in uz_df.columns) else ""

                    if isinstance(adp_col_resolved, str) and adp_col_resolved.startswith("__CONST__:"):
                        adp_val = adp_col_resolved.split(":", 1)[1]
                        adp_col_missing = False
                    else:
                        adp_col_missing = (adp_col_resolved not in ad_df.columns)
                        adp_val = ad_df.loc[ad_idx, adp_col_resolved] if (ad_idx is not None and not adp_col_missing) else ""

                    if ad_idx is None and uz_idx is not None:
                        status = "Employee ID Not Found in ADP"
                    elif ad_idx is not None and uz_idx is None:
                        status = "Employee ID Not Found in Uzio"
                    elif adp_col_missing:
                        status = "Column Missing in ADP Sheet"
                    elif uz_field not in uz_df.columns:
                        status = "Column Missing in Uzio Sheet"
                    else:
                        uz_n = norm_value(uz_val, uz_field)
                        ad_n = norm_value(adp_val, uz_field)

                        if is_fuzzy_match(uz_n, ad_n):
                            status = "Data Match"
                        elif uz_n == "" and ad_n != "":
                            status = "Value missing in Uzio (ADP has value)"
                        elif uz_n != "" and ad_n == "":
                            status = "Value missing in ADP (Uzio has value)"
                        else:
                            status = "Data Mismatch"

                    rows.append(
                        {
                            "Employee ID": employee_id_out,
                            "Section": section,
                            "Field": uz_field,
                            "UZIO_Value": uz_val,
                            "ADP_Value": adp_val,
                            "ADP_SourceOfTruth_Status": status,
                        }
                    )

        comparison_detail = pd.DataFrame(
            rows,
            columns=["Employee ID", "Section", "Field", "UZIO_Value", "ADP_Value", "ADP_SourceOfTruth_Status"],
        )

        # Field summary
        if len(comparison_detail):
            comparison_detail["_FieldKey"] = comparison_detail["Section"] + " :: " + comparison_detail["Field"]

            statuses = [
                "Data Match",
                "Data Mismatch",
                "Value missing in Uzio (ADP has value)",
                "Value missing in ADP (Uzio has value)",
                "Employee ID Not Found in Uzio",
                "Employee ID Not Found in ADP",
                "Column Missing in ADP Sheet",
                "Column Missing in Uzio Sheet",
            ]
            field_summary_by_status = (
                comparison_detail.pivot_table(
                    index="_FieldKey",
                    columns="ADP_SourceOfTruth_Status",
                    values="Employee ID",
                    aggfunc="count",
                    fill_value=0,
                )
                .reindex(columns=statuses, fill_value=0)
                .reset_index()
                .rename(columns={"_FieldKey": "Field"})
            )
            field_summary_by_status["Total"] = field_summary_by_status[statuses].sum(axis=1)
        else:
            field_summary_by_status = pd.DataFrame(
                columns=[
                    "Field",
                    "Data Match",
                    "Data Mismatch",
                    "Value missing in Uzio (ADP has value)",
                    "Value missing in ADP (Uzio has value)",
                    "Employee ID Not Found in Uzio",
                    "Employee ID Not Found in ADP",
                    "Column Missing in ADP Sheet",
                    "Column Missing in Uzio Sheet",
                    "Total",
                ]
            )

        # Remove requested columns from Field_Summary_By_Status
        field_summary_by_status = drop_unwanted_field_summary_columns(field_summary_by_status)

        # Remove FieldKey helper from Comparison_Detail_AllFields output
        if "_FieldKey" in comparison_detail.columns:
            comparison_detail = comparison_detail.drop(columns=["_FieldKey"])

        # Summary
        uzio_emp = set(uz_df[emp_key_uz].dropna().map(str)) if (len(uz_df) and emp_key_uz in uz_df.columns) else set()
        adp_emp = set(ad_df[emp_key_ad].dropna().map(str)) if (len(ad_df) and emp_key_ad in ad_df.columns) else set()

        summary = pd.DataFrame(
            {
                "Metric": [
                    "Section",
                    "Total UZIO Employees",
                    "Total ADP Employees",
                    "Employees in both",
                    "Employees only in UZIO",
                    "Employees only in ADP",
                    "Total UZIO Records",
                    "Total ADP Records",
                    "Fields Compared",
                    "Total Comparisons (field-level rows)",
                ],
                "Value": [
                    section,
                    len(uzio_emp),
                    len(adp_emp),
                    len(uzio_emp & adp_emp),
                    len(uzio_emp - adp_emp),
                    len(adp_emp - uzio_emp),
                    len(uz_df),
                    len(ad_df),
                    int(sec_map.shape[0]),
                    int(comparison_detail.shape[0]),
                ],
            }
        )

        out = io.BytesIO()
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            summary.to_excel(writer, sheet_name="Summary", index=False)
            field_summary_by_status.to_excel(writer, sheet_name="Field_Summary_By_Status", index=False)
            comparison_detail.to_excel(writer, sheet_name="Comparison_Detail_AllFields", index=False)

        return out.getvalue()

    payment_bytes = build_report_for_section(
        section="Payment",
        uz_df=uzio_pay,
        ad_df=adp_pay,
        g_uz=g_uz_pay,
        g_ad=g_ad_pay,
        emp_key_uz=UZIO_KEY,
        emp_key_ad=ADP_PAY_KEY,
        mapping_df=pay_map,
    )

    emergency_contact_bytes = build_report_for_section(
        section="Emergency Contact",
        uz_df=uzio_ec,
        ad_df=adp_ec,
        g_uz=g_uz_ec,
        g_ad=g_ad_ec,
        emp_key_uz=UZIO_KEY,
        emp_key_ad=ADP_EC_KEY,
        mapping_df=ec_map,
    )

    return {"payment": payment_bytes, "emergency_contact": emergency_contact_bytes}


# ---------- UI ----------

def render_ui():
    st.title(APP_TITLE)
    st.write("Upload the Excel workbook (.xlsx). The tool will generate two independent reports (Payment + Emergency Contact).")

    uploaded_file = st.file_uploader("Upload Excel workbook", type=["xlsx"])
    run_btn = st.button("Run Audit", type="primary", disabled=(uploaded_file is None))

    if run_btn:
        try:
            with st.spinner("Running audit..."):
                reports = run_comparison(uploaded_file.getvalue())

            st.success("Reports generated (Payment + Emergency Contact).")

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            payment_name = f"UZIO_vs_ADP_Payment_Report_ADP_SourceOfTruth_{ts}.xlsx"
            ec_name = f"UZIO_vs_ADP_EmergencyContact_Report_ADP_SourceOfTruth_{ts}.xlsx"

            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    label="Download Payment Report (.xlsx)",
                    data=reports["payment"],
                    file_name=payment_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                )
            with col2:
                st.download_button(
                    label="Download Emergency Contact Report (.xlsx)",
                    data=reports["emergency_contact"],
                    file_name=ec_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                )

        except Exception as e:
            st.error(f"Failed: {e}")

if __name__ == "__main__":
    st.set_page_config(page_title=APP_TITLE, layout="centered", initial_sidebar_state="collapsed")
    render_ui()
