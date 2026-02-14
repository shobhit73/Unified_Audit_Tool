import pandas as pd
import os

adp_path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\ADP Cenus File.xlsx"

if os.path.exists(adp_path):
    print(f"Reading: {adp_path}")
    df = pd.read_excel(adp_path)
    if 'Position Status' in df.columns:
        print("\nPosition Status head:")
        print(df['Position Status'].head(20))
        print("\nUnique values in Position Status:")
        print(df['Position Status'].unique())
    else:
        print("\nPosition Status NOT FOUND")
else:
    print(f"File not found: {adp_path}")
