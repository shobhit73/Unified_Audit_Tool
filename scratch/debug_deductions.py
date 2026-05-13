import pandas as pd
file_path = r'C:\Users\shobhit.sharma\Downloads\J4 Prior Payroll Setup\Payroll History_Q1.xlsx'
try:
    df_ded = pd.read_excel(file_path)
    all_cols_ded = list(df_ded.columns)
    total_earn_col = next((c for c in all_cols_ded if c.strip().upper() == 'TOTAL EARNINGS'), None)
    fed_taxable_col = next((c for c in all_cols_ded if 'FEDERAL INCOME - EMPLOYEE TAXABLE' in c.upper()), None)
    ded_cols_raw = [c for c in all_cols_ded if 'VOLUNTARY DEDUCTION' in c.upper() and 'TOTAL' not in c.upper() and 'REV' not in c.upper()]
    
    non_null_rows = df_ded[df_ded[total_earn_col].notna()]
    with open("scratch/debug_out.txt", "w") as f:
        f.write(f"Columns: {all_cols_ded}\n")
        f.write(f"Number of non-null rows in {total_earn_col}: {len(non_null_rows)}\n")
        f.write("First 5 rows of all columns:\n")
        f.write(df_ded.head().to_string() + "\n")

        
        # Look at the first 5 rows to see what's in these columns
        print(df_ded[[total_earn_col, fed_taxable_col]].head(15))
        
        df_valid = df_ded[df_ded[total_earn_col].notna() & df_ded[fed_taxable_col].notna() & (pd.to_numeric(df_ded[total_earn_col], errors='coerce') < 100000)].copy()
        print(f'Rows after notna filter: {len(df_valid)}')
        
        df_valid['_GAP'] = (df_valid[total_earn_col] - df_valid[fed_taxable_col]).round(2)
        print(f'Rows with GAP >= 0: {len(df_valid[df_valid["_GAP"] >= 0])}')
        print(f'GAP values: {df_valid["_GAP"].head(10).tolist()}')
        
        df_valid = df_valid[df_valid['_GAP'] >= 0]
        
        # Check active deductions
        for i, (_, row) in enumerate(df_valid.iterrows()):
            active = {col: row[col] for col in ded_cols_raw if pd.notna(row[col]) and row[col] > 0}
            print(f'Row {i} active deductions: {active}')
            if i > 5: break
except Exception as e:
    import traceback
    traceback.print_exc()
