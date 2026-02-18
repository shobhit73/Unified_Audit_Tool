
import pandas as pd
import numpy as np
import re

# ==========================================
# MOCKING HELPERS
# ==========================================

def norm_blank(x):
    if x is None:
        return ""
    if isinstance(x, float) and np.isnan(x):
        return ""
    if isinstance(x, str) and x.strip().lower() in {"", "nan", "none", "null"}:
        return ""
    return x

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

def _safe_percentage(x):
    x = norm_blank(x)
    if x == "":
        return np.nan
    try:
        if isinstance(x, str):
            s = x.strip().replace(",", "").replace("$", "")
            if "%" in s:
                s = s.replace("%", "")
                return float(s)
            f = float(s)
            if 0 < abs(f) <= 1.0:
                 return f * 100.0
            return f
        if isinstance(x, (int, float, np.integer, np.floating)):
            f = float(x)
            if 0 < abs(f) <= 1.0:
                return f * 100.0
            return f
        return np.nan
    except Exception:
        return np.nan

def find_col(df_cols, *candidate_names):
    norm_map = {c.strip().casefold(): c for c in df_cols}
    for cand in candidate_names:
        key = cand.strip().casefold()
        if key in norm_map:
            return norm_map[key]
    return None

def normalize_adp_payment_table_ORIGINAL(adp_pay: pd.DataFrame, emp_col: str) -> pd.DataFrame:
    df = adp_pay.copy()
    dep_type_col = "DEPOSIT TYPE"
    dep_pct_col = "DEPOSIT PERCENT"
    
    df["Paycheck Percentage"] = ""
    df["_row_ord"] = np.arange(len(df))

    for emp, g in df.groupby(emp_col, sort=False):
        idxs = list(g.index)
        cats = []
        for i in idxs:
            dt = str(norm_blank(df.at[i, dep_type_col])).strip().casefold()
            if "full" in dt:
                cat = "full"
            else:
                cat = "other"
            cats.append(cat)
        
        # Simplified logic for test
        full_pct = 100.0 

        for i, c in zip(idxs, cats):
            if c == "full":
                df.at[i, "Paycheck Percentage"] = full_pct # ORIGINAL: Auto-assigns 100.0
            
    df.drop(columns=["_row_ord"], inplace=True)
    return df

def normalize_adp_payment_table_PROPOSED(adp_pay: pd.DataFrame, emp_col: str) -> pd.DataFrame:
    df = adp_pay.copy()
    dep_type_col = "DEPOSIT TYPE"
    dep_pct_col = "DEPOSIT PERCENT"
    
    df["Paycheck Percentage"] = ""
    df["_row_ord"] = np.arange(len(df))

    for emp, g in df.groupby(emp_col, sort=False):
        idxs = list(g.index)
        cats = []
        for i in idxs:
            dt = str(norm_blank(df.at[i, dep_type_col])).strip().casefold()
            if "full" in dt:
                cat = "full"
            else:
                cat = "other"
            cats.append(cat)
        
        full_pct = 100.0

        for i, c in zip(idxs, cats):
            if c == "full":
                # PROPOSED CHANGE:
                # Check if source percent is blank
                src_pct = norm_blank(df.at[i, dep_pct_col])
                if src_pct == "":
                     df.at[i, "Paycheck Percentage"] = "" # Leave blank
                else:
                     df.at[i, "Paycheck Percentage"] = full_pct # Or use src_pct? 
                     # For now, let's assume if explicit value exists we might want it, 
                     # but typically Full has none. If user put 100%, we might keep it.
                     # But key request is: if blank, keep blank.
    
    df.drop(columns=["_row_ord"], inplace=True)
    return df

# TEST DATA
data = {
    "ASSOCIATE ID": ["EMP001", "EMP001"],
    "DEPOSIT TYPE": ["Partial", "Full"],
    "DEPOSIT PERCENT": ["", ""] # Both blank
}
df = pd.DataFrame(data)

print("--- ORIGINAL Logic ---")
df_orig = normalize_adp_payment_table_ORIGINAL(df, "ASSOCIATE ID")
print(df_orig[["DEPOSIT TYPE", "Paycheck Percentage"]])

print("\n--- PROPOSED Logic ---")
df_prop = normalize_adp_payment_table_PROPOSED(df, "ASSOCIATE ID")
print(df_prop[["DEPOSIT TYPE", "Paycheck Percentage"]])

res_orig = df_orig.iloc[1]["Paycheck Percentage"]
res_prop = df_prop.iloc[1]["Paycheck Percentage"]

if res_orig == 100.0 and res_prop == "":
    print("\nSUCCESS: Reproduction and fix logic confirmed.")
else:
    print(f"\nFAILURE: Orig={res_orig}, Prop={res_prop}")
