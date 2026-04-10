import pandas as pd
import os

files = [
    r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Sample Custom Reports\Falcon\Paycom_Falcon_Census_28th_March.xlsx",
    r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Sample Payment Data\New folder\UZIO_payment_method.xlsx",
    r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\License Sample\Emergency and Licence Report.xlsx"
]

for f in files:
    if os.path.exists(f):
        print(f"\n=== File: {os.path.basename(f)} ===")
        try:
            xl = pd.ExcelFile(f)
            for sheet in xl.sheet_names:
                print(f"--- Sheet: {sheet} ---")
                df = pd.read_excel(f, sheet_name=sheet, nrows=0)
                print(f"Columns: {df.columns.tolist()}")
        except Exception as e:
            print(f"Error reading {f}: {e}")
    else:
        print(f"File not found: {f}")
