import pandas as pd
import os

path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Paycom Cenus Sample\Pria Paycom Cenus.xlsx"

if os.path.exists(path):
    print(f"Reading: {path}")
    # Read without dtype forcing first to see native types
    df_raw = pd.read_excel(path)
    
    # Identify Emp Code col
    col = next((c for c in df_raw.columns if "Employee_Code" in c or "Emp Code" in c), None)
    
    if col:
        print(f"Found column: '{col}'")
        print("First 20 values (Raw & Type):")
        for x in df_raw[col].head(20):
            print(f"Val: {repr(x)} | Type: {type(x)}")
    else:
        print("Employee_Code column not found.")
else:
    print(f"File not found: {path}")
