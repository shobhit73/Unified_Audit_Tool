import pandas as pd

def deduplicate_adp(df: pd.DataFrame, key_col: str) -> pd.DataFrame:
    col_map = {c: c.lower() for c in df.columns}
    status_col = next((c for c, l in col_map.items() if "position status" in l), None)
    
    def pick_best(group):
        if len(group) <= 1:
            return group.iloc[[0]]
        
        group = group.copy()
        group['__norm_status'] = group[status_col].astype(str).str.lower().str.strip()
        actives = group[group['__norm_status'] == 'active']
        
        if not actives.empty:
            return actives.iloc[[0]]
        return group.iloc[[0]]

    print("Before deduplicate columns:", df.columns.tolist())
    deduped = df.groupby(key_col, as_index=False, group_keys=False).apply(pick_best)
    deduped = deduped.reset_index(drop=True)
    print("After deduplicate columns:", deduped.columns.tolist())
    
    cols_to_drop = [c for c in ['__norm_status', '__has_loc'] if c in deduped.columns]
    if cols_to_drop:
        deduped = deduped.drop(columns=cols_to_drop)
        
    return deduped

data = {
    'Associate ID': ['A1', 'A1', 'A2'],
    'Position Status': ['Terminated', 'Active', 'Active'],
    'Legal First Name': ['John', 'John', 'Jane'],
    'Legal Last Name': ['Smith', 'Smith', 'Doe']
}
df = pd.DataFrame(data)

deduped = deduplicate_adp(df, 'Associate ID')
print("Returned deduped columns:", deduped.columns.tolist())
