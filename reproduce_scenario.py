
import pandas as pd
import numpy as np
import re

# ==========================================
# MOCKS
# ==========================================

def norm_blank(x):
    if x is None: return ""
    if isinstance(x, float) and np.isnan(x): return ""
    if isinstance(x, str) and x.strip().lower() in {"", "nan", "none", "null"}: return ""
    return x

def norm_distribution_token(val: str) -> str:
    v = norm_blank(val)
    if v == "": return ""
    s = str(v).strip().casefold()
    if "flat dollar" in s or "flat amount" in s or ("flat" in s and "dollar" in s):
        return "amount"
    return s

def _is_blank_money_or_percent(v) -> bool:
    s = str(norm_blank(v)).strip()
    if s == "": return True
    s2 = s.replace("$", "").replace(",", "").replace("%", "").strip()
    if s2 == "": return True
    try:
        if float(s2) == 0.0: return True
    except: pass
    return False

def _safe_percentage(x):
    x = norm_blank(x)
    if x == "": return np.nan
    try:
        if isinstance(x, str):
            s = x.strip().replace(",", "").replace("$", "").replace("%", "")
            return float(s)
        return float(x)
    except: return np.nan

def normalize_adp_payment_table_PROPOSED(adp_pay: pd.DataFrame, emp_col: str) -> pd.DataFrame:
    df = adp_pay.copy()
    dep_type_col = "DEPOSIT TYPE"
    dep_pct_col = "DEPOSIT PERCENT"
    
    df["Paycheck Percentage"] = ""

    for emp, g in df.groupby(emp_col, sort=False):
        idxs = list(g.index)
        
        # 1. Analyze Pass
        cats = []
        for i in idxs:
            dt = str(norm_blank(df.at[i, dep_type_col])).strip().casefold()
            if "partial" in dt and ("%" in dt or "percent" in str(df.at[i, dep_pct_col]).lower()):
                 cat = "partial_pct" # Simplified mock detection
            elif "partial" in dt:
                 cat = "partial_amt"
            elif "full" in dt:
                 cat = "full"
            else:
                 cat = "other"
            cats.append(cat)

        has_partial_pct = any(c == "partial_pct" for c in cats)
        sum_partial_pct = 0.0
        if has_partial_pct:
            for i, c in zip(idxs, cats):
                if c == "partial_pct":
                    v = _safe_percentage(df.at[i, dep_pct_col])
                    if not np.isnan(v): sum_partial_pct += v
        
        full_pct = max(0.0, 100.0 - sum_partial_pct) if has_partial_pct else 100.0

        # 2. Assign Pass
        for i, c in zip(idxs, cats):
            if c == "full":
                if has_partial_pct:
                    # Logic 2: Partial % exists -> Force remainder
                    df.at[i, "Paycheck Percentage"] = full_pct
                else:
                    # Logic 1: No Partial % -> Check blank
                    src = norm_blank(df.at[i, dep_pct_col])
                    if src == "":
                        df.at[i, "Paycheck Percentage"] = ""
                    else:
                        df.at[i, "Paycheck Percentage"] = full_pct
            elif c == "partial_pct":
                 val = _safe_percentage(df.at[i, dep_pct_col])
                 df.at[i, "Paycheck Percentage"] = val
    return df


# ==========================================
# TESTS
# ==========================================

print("--- TEST 1: ADP Full + Partial % (Scenario 2) ---")
# Expected: Full row gets 100 - 75 = 25
adp_data_1 = {
    "ASSOCIATE ID": ["A1", "A1"],
    "DEPOSIT TYPE": ["Partial %", "Full"],
    "DEPOSIT PERCENT": ["75", ""] 
}
df1 = pd.DataFrame(adp_data_1)
res1 = normalize_adp_payment_table_PROPOSED(df1, "ASSOCIATE ID")
print(res1[["DEPOSIT TYPE", "Paycheck Percentage"]])
val_full_1 = res1.iloc[1]["Paycheck Percentage"]
print(f"Full Row: {val_full_1} (Expect 25.0)")


print("\n--- TEST 2: ADP Full + Partial Amount (Scenario 1) ---")
# Expected: Full row remains blank (no partial % to force remainder logic)
adp_data_2 = {
    "ASSOCIATE ID": ["A2", "A2"],
    "DEPOSIT TYPE": ["Partial", "Full"],
    "DEPOSIT PERCENT": ["", ""] # Partial is Amount-based (implied by blank pct in mock)
}
df2 = pd.DataFrame(adp_data_2)
res2 = normalize_adp_payment_table_PROPOSED(df2, "ASSOCIATE ID")
print(res2[["DEPOSIT TYPE", "Paycheck Percentage"]])
val_full_2 = res2.iloc[1]["Paycheck Percentage"]
print(f"Full Row: '{val_full_2}' (Expect '')")

if val_full_1 == 25.0 and val_full_2 == "":
    print("\nSUCCESS: Both ADP scenarios correct.")
else:
    print("\nFAILURE.")
