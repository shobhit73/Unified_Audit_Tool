import pandas as pd
import os

path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Sample Payment Data\HR Report_2026-02-13-05-00-13.xlsx"

if os.path.exists(path):
    print(f"Reading: {path}")
    # User said first row needs to be removed. So header might be row 1 (0-indexed) or row 2?
    # Let's read first few rows without header to see.
    df_raw = pd.read_excel(path, header=None, nrows=5)
    print("First 5 rows (raw):")
    print(df_raw)
    
    # Try reading with header=1 (skipping row 0)
    print("\nReading with header=1:")
    df = pd.read_excel(path, header=1)
    print("Columns:")
    for c in df.columns:
        print(f"'{c}'")
else:
    print(f"File not found: {path}")
