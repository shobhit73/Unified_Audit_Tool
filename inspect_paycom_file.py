import pandas as pd
import os

path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Paycom Cenus File.csv"

if os.path.exists(path):
    print(f"Reading: {path}")
    try:
        try:
             df = pd.read_csv(path, dtype=str)
        except:
             df = pd.read_csv(path, dtype=str, encoding='latin1')
             
        print("Columns found:")
        for c in df.columns:
            print(f"'{c}'")
            
        print("\nColumns containing Reason:")
        cols = [c for c in df.columns if "Reason" in str(c)]
        for c in cols:
            print(f"'{c}'")
            
    except Exception as e:
        print(f"Error reading csv: {e}")
else:
    print(f"File not found: {path}")
