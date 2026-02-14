import pandas as pd
import re
import numpy as np

# Helpers from census_audit_app.py
def norm_colname(c: str) -> str:
    if c is None:
        return ""
    c = str(c).replace("\n", " ").replace("\r", " ")
    c = c.replace("\u00A0", " ")
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

def deduplicate_adp(df: pd.DataFrame, key_col: str) -> pd.DataFrame:
    # Identify special columns (normalized)
    col_map = {c: c.lower() for c in df.columns}
    
    status_col = next((c for c, l in col_map.items() if "position status" in l), None)
    term_date_col = next((c for c, l in col_map.items() if "termination date" in l), None)
    start_date_col = next((c for c, l in col_map.items() if "position start date" in l), None)
    loc_desc_col = next((c for c, l in col_map.items() if "work location description" in l), None)
    license_id_col = next((c for c, l in col_map.items() if "license/certification id" in l), None)
    
    print(f"DEBUG: status_col identified as: {status_col}")

    # If we can't find status col, fallback to basic drop_duplicates
    if not status_col:
        return df.drop_duplicates(subset=[key_col], keep="first")
        
    def pick_best(group):
        if len(group) <= 1:
            return group.iloc[[0]]
        
        # Helper to parse date for sorting
        def get_date_val(row, col):
            if not col or pd.isna(row[col]):
                return pd.Timestamp.min
            val = str(row[col]).strip()
            if not val:
                return pd.Timestamp.min
            try:
                return pd.to_datetime(val)
            except:
                return pd.Timestamp.min

        if isinstance(group, pd.Series):
             return group.to_frame().T

        group = group.copy()
        group['__norm_status'] = group[status_col].astype(str).str.lower().str.strip()
        
        # Add license check
        if license_id_col:
            group['__has_license'] = group[license_id_col].apply(lambda x: 1 if norm_blank(x) != "" else 0)
        else:
            group['__has_license'] = 0

        actives = group[group['__norm_status'] == 'active']
        terms = group[group['__norm_status'] == 'terminated']
        others = group[(group['__norm_status'] != 'active') & (group['__norm_status'] != 'terminated')]
        
        # Logic 1: If Actives exist, prioritize them
        if not actives.empty:
            # Rule: select row where Work Location Description is not blank
            actives['__sort_date'] = actives.apply(lambda r: get_date_val(r, start_date_col), axis=1)

            if loc_desc_col:
                actives['__has_loc'] = actives[loc_desc_col].apply(lambda x: 1 if norm_blank(x) != "" else 0)
                best_active = actives.sort_values(by=['__has_loc', '__has_license', '__sort_date'], ascending=[False, False, False]).iloc[[0]]
            else:
                best_active = actives.sort_values(by=['__has_license', '__sort_date'], ascending=[False, False]).iloc[[0]]
            
            return best_active

        # Logic 2: Terminated
        if not terms.empty:
            # Rule: If term dates are different, select latest.
            # Rule: If one blank and one value -> select latest Position Start Date
            
            # Check for blank term dates
            terms['__sort_date'] = pd.Timestamp.min
            
            # Determine which date to sort by mainly
            use_start_date = False
            if term_date_col:
                terms['__term_dt_val'] = terms[term_date_col].apply(norm_blank)
                has_blank = (terms['__term_dt_val'] == "").any()
                has_val = (terms['__term_dt_val'] != "").any()
                
                if has_blank and has_val:
                    use_start_date = True
            else:
                use_start_date = True

            if use_start_date:
                 terms['__sort_date'] = terms.apply(lambda r: get_date_val(r, start_date_col), axis=1)
            elif term_date_col:
                 terms['__sort_date'] = terms.apply(lambda r: get_date_val(r, term_date_col), axis=1)
            
            # Add License priority to Terminated as well (implicitly safe)
            return terms.sort_values(by=['__has_license', '__sort_date'], ascending=[False, False]).iloc[[0]]

        # Fallback (Others, e.g. Leave)
        if not others.empty:
             others['__sort_date'] = others.apply(lambda r: get_date_val(r, start_date_col), axis=1)
             return others.sort_values(by=['__has_license', '__sort_date'], ascending=[False, False]).iloc[[0]]

        return group.iloc[[0]]

    # Apply grouping
    deduped = df.groupby(key_col, group_keys=False).apply(pick_best)
    
    # Cleanup temp columns if they leaked (apply usually returns pure subset but safe to drop)
    cols_to_drop = [c for c in ['__norm_status', '__has_loc', '__sort_date', '__term_dt_val', '__has_license'] if c in deduped.columns]
    if cols_to_drop:
        deduped = deduped.drop(columns=cols_to_drop)
        
    return deduped

# Main simulation
adp_path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\ADP Cenus File.xlsx"
print(f"Reading: {adp_path}")
adp = pd.read_excel(adp_path, dtype=str)

print(f"Original shape: {adp.shape}")
adp.columns = [norm_colname(c) for c in adp.columns]
print(f"Normalized columns: {list(adp.columns)}")

if "Position Status" in adp.columns:
    print("Position Status FOUND in normalized columns.")
    print(adp["Position Status"].head())
else:
    print("Position Status NOT FOUND in normalized columns.")

ADP_KEY = "Associate ID"
if ADP_KEY in adp.columns:
    print(f"Deduplicating on {ADP_KEY}...")
    adp_deduped = deduplicate_adp(adp, ADP_KEY)
    print(f"Deduped shape: {adp_deduped.shape}")
    
    if "Position Status" in adp_deduped.columns:
        print("Position Status FOUND in deduped columns.")
        print(adp_deduped["Position Status"].head(10))
        print("Unique values:", adp_deduped["Position Status"].unique())
        
        # Write unique values to file to be sure
        with open("adp_deduped_status.txt", "w") as f:
             f.write(str(adp_deduped["Position Status"].unique()))
    else:
        print("Position Status NOT FOUND in deduped columns.")
else:
    print(f"{ADP_KEY} not found.")
