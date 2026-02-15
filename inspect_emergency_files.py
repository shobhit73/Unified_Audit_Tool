import pandas as pd
import os

f_uzio = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Uzio Emergeency Input File.xlsx"
f_adp = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\ADP Emegerncy Input .xlsx"

def inspect(path):
    if os.path.exists(path):
        print(f"\nScanning: {os.path.basename(path)}")
        try:
            df = pd.read_excel(path)
            print(f"Columns: {list(df.columns)}")
            print("First 3 rows:")
            print(df.head(3).to_string())
        except Exception as e:
            # Try header=1 if header=0 looks empty
            try:
                df = pd.read_excel(path, header=1)
                print(f"Columns (Header=1): {list(df.columns)}")
                print("First 3 rows:")
                print(df.head(3).to_string())
            except:
                print(f"Error reading: {e}")
    else:
        print(f"File not found: {path}")

inspect(f_uzio)
inspect(f_adp)
