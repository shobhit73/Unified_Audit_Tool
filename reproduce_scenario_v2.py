
import pandas as pd
import numpy as np

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
    
def _safe_float(x):
    x = norm_blank(x)
    if x == "": return np.nan
    try:
        if isinstance(x, str):
            s = x.strip().replace(",", "").replace("$", "")
            return float(s)
        return float(x)
    except: return np.nan

# ==========================================
# PROPOSED IMPLEMENTATIONS
# ==========================================

def normalize_adp_payment_table_PROPOSED(adp_pay: pd.DataFrame, emp_col: str) -> pd.DataFrame:
    df = adp_pay.copy()
    dep_type_col = "DEPOSIT TYPE"
    dep_pct_col = "DEPOSIT PERCENT"
    
    df["Paycheck Percentage"] = ""

    for emp, g in df.groupby(emp_col, sort=False):
        idxs = list(g.index)
        
        # 1. Analyze
        cats = []
        for i in idxs:
            dt = str(norm_blank(df.at[i, dep_type_col])).strip().casefold()
            if "partial" in dt and ("%" in dt or "percent" in str(df.at[i, dep_pct_col]).lower()):
                 cat = "partial_pct"
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

        # 2. Assign
        is_single_row = (len(idxs) == 1)
        
        for i, c in zip(idxs, cats):
            if is_single_row:
                # Rule 1: Single Row -> 100%
                df.at[i, "Paycheck Percentage"] = 100.0
            
            elif c == "full":
                if has_partial_pct:
                    # Rule 2: Multi + Partial % -> Remainder
                    df.at[i, "Paycheck Percentage"] = full_pct
                else:
                    # Rule 3: Multi + No Partial % -> Blank (if source blank)
                    src = norm_blank(df.at[i, dep_pct_col])
                    if src == "":
                        df.at[i, "Paycheck Percentage"] = ""
                    else:
                        df.at[i, "Paycheck Percentage"] = full_pct
            
            elif c == "partial_pct":
                 val = _safe_percentage(df.at[i, dep_pct_col])
                 df.at[i, "Paycheck Percentage"] = val
    return df

def normalize_uzio_payment_full_inference_PROPOSED(uzio_pay: pd.DataFrame, emp_col: str) -> pd.DataFrame:
    df = uzio_pay.copy()
    dist_col = "Paycheck Distribution"
    pct_col = "Paycheck Percentage"
    amt_col = "Paycheck Amount"

    for emp, g in df.groupby(emp_col, sort=False):
        
        # NEW: Single Row Logic
        if len(g) == 1:
            idx = g.index[0]
            # Rule 1: Single Row -> 100%
            df.at[idx, dist_col] = "Percentage"
            df.at[idx, pct_col] = 100.0
            continue

        if len(g) < 2:
            continue

        candidate_idxs = []
        for i in g.index:
            # Rule 4: Skip Flat Dollar explicitly
            d_val = df.at[i, dist_col]
            if norm_distribution_token(d_val) == "amount":
                continue

            if _is_blank_money_or_percent(df.at[i, amt_col]) and _is_blank_money_or_percent(df.at[i, pct_col]):
                candidate_idxs.append(i)

        if len(candidate_idxs) != 1:
            continue

        full_idx = candidate_idxs[0]
        # Calculate remainder logic (simplified for test)
        df.at[full_idx, pct_col] = 100.0 
        df.at[full_idx, dist_col] = "Percentage"

    return df

# ==========================================
# TESTS
# ==========================================

print("--- TEST SET ---")

# ADP 1: Single Row Full (Blank Source) -> 100
t1 = pd.DataFrame({"ASSOCIATE ID": ["A1"], "DEPOSIT TYPE": ["Full"], "DEPOSIT PERCENT": [""]})
r1 = normalize_adp_payment_table_PROPOSED(t1, "ASSOCIATE ID").iloc[0]["Paycheck Percentage"]
print(f"ADP Single: {r1} (Expect 100.0)")

# ADP 2: Multi + Partial Amt (Blank Source) -> Blank
t2 = pd.DataFrame({"ASSOCIATE ID": ["A2", "A2"], "DEPOSIT TYPE": ["Partial", "Full"], "DEPOSIT PERCENT": ["", ""]})
r2 = normalize_adp_payment_table_PROPOSED(t2, "ASSOCIATE ID").iloc[1]["Paycheck Percentage"]
print(f"ADP Multi (Amt): '{r2}' (Expect '')")

# ADP 3: Multi + Partial % (Blank Source) -> Remainder
t3 = pd.DataFrame({"ASSOCIATE ID": ["A3", "A3"], "DEPOSIT TYPE": ["Partial %", "Full"], "DEPOSIT PERCENT": ["75", ""]})
r3 = normalize_adp_payment_table_PROPOSED(t3, "ASSOCIATE ID").iloc[1]["Paycheck Percentage"]
print(f"ADP Multi (%): {r3} (Expect 25.0)")

# Uzio 1: Single Row (Flat Dollar) -> 100
t4 = pd.DataFrame({
    "Employee ID": ["E1"], 
    "Paycheck Distribution": ["Flat Dollar"], 
    "Paycheck Amount": [""], 
    "Paycheck Percentage": [""]
})
r4 = normalize_uzio_payment_full_inference_PROPOSED(t4, "Employee ID").iloc[0]["Paycheck Percentage"]
print(f"Uzio Single: {r4} (Expect 100.0)")

# Uzio 2: Multi (Flat Dollar + Flat Dollar) -> No Inference
t5 = pd.DataFrame({
    "Employee ID": ["E2", "E2"], 
    "Paycheck Distribution": ["Flat Dollar", "Flat Dollar"], 
    "Paycheck Amount": ["100", ""], 
    "Paycheck Percentage": ["", ""]
})
res5 = normalize_uzio_payment_full_inference_PROPOSED(t5, "Employee ID")
r5 = res5.iloc[1]["Paycheck Percentage"]
print(f"Uzio Multi: '{r5}' (Expect '')")

success = (r1==100.0 and r2=="" and r3==25.0 and r4==100.0 and r5=="")
print(f"\nOVERALL SUCCESS: {success}")
