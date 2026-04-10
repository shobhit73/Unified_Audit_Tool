import pandas as pd
import os

files = [
    'JM_Parcel_Earnings_mapping.xlsx',
    'JM_Parcel_deductions_mapping.xlsx',
    'JM_Parcel_taxes_mapping.xlsx'
]

dir_path = r'C:\Users\rohit.kaushik\Downloads\Unified Audit Tool'

for f in files:
    path = os.path.join(dir_path, f)
    if os.path.exists(path):
        df = pd.read_excel(path, nrows=2)
        print(f"\n--- {f} ---")
        print(df.columns.tolist())
    else:
        print(f"\n--- {f} NOT FOUND ---")
