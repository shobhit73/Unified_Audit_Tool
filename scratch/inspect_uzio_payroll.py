import pandas as pd
import os

file_path = r'C:\Users\rohit.kaushik\Downloads\Unified Audit Tool\Prior Payroll Register Report_2026-04-02-04-06-15.xlsx'

if os.path.exists(file_path):
    print(f"File exists: {file_path}")
    # Read first 10 rows to see where headers start
    df_peek = pd.read_excel(file_path, header=None, nrows=10)
    print("\n--- First 10 rows (Raw) ---")
    print(df_peek)
    
    # Try to find a row with common headers
    header_row = 0
    for i, row in df_peek.iterrows():
        row_str = " ".join([str(x).lower() for x in row if pd.notna(x)])
        if "employee name" in row_str or "employee id" in row_str:
            header_row = i
            print(f"\nPotential header row found at index: {header_row}")
            break
            
    df_actual = pd.read_excel(file_path, header=header_row)
    print("\n--- Columns found ---")
    print(df_actual.columns.tolist()[:20]) # Print first 20 columns
    
else:
    print(f"File NOT found: {file_path}")
