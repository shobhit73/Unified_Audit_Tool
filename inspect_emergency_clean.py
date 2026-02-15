import pandas as pd
import os

f_uzio = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Uzio Emergeency Input File.xlsx"
f_adp = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\ADP Emegerncy Input .xlsx"

def inspect(path, name):
    if os.path.exists(path):
        print(f"\n--- {name} ---")
        try:
            # Try default header
            df = pd.read_excel(path)
            cols = sorted([str(c).strip() for c in df.columns])
            print(f"Columns (Header=0): {cols}")
            
            # If header 0 looks like data (e.g. unnamed columns), try header 1
            if len([c for c in cols if "Unnamed" in c]) > 2:
                df = pd.read_excel(path, header=1)
                cols = sorted([str(c).strip() for c in df.columns])
                print(f"Columns (Header=1): {cols}")
                
        except Exception as e:
            print(f"Error: {e}")
    else:
        print(f"File not found: {path}")

inspect(f_uzio, "UZIO")
inspect(f_adp, "ADP")
