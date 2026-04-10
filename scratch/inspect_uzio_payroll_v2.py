import pandas as pd
import os

file_path = r'C:\Users\rohit.kaushik\Downloads\Unified Audit Tool\Prior Payroll Register Report_2026-04-02-04-06-15.xlsx'

if os.path.exists(file_path):
    print(f"File exists: {file_path}")
    # Read first 50 rows
    df_peek = pd.read_excel(file_path, header=None, nrows=50)
    
    header_row = 0
    found = False
    for i, row in df_peek.iterrows():
        row_str = " ".join([str(x).lower() for x in row if pd.notna(x)])
        # Uzio registers often have "Employee Name" or "Earnings" or "Total"
        if "employee name" in row_str or "employee id" in row_str:
            header_row = i
            found = True
            print(f"\nPotential header row found at index: {header_row}")
            print(f"Row content: {list(row)}")
            break
            
    if not found:
        print("\nCould not find 'Employee Name' or 'Employee ID' in first 50 rows.")
        # Print some rows to see what's there
        print(df_peek.tail(10))
    else:
        df_actual = pd.read_excel(file_path, header=header_row)
        print("\n--- Columns found ---")
        print(df_actual.columns.tolist())
    
else:
    print(f"File NOT found: {file_path}")
