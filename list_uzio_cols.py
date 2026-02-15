import pandas as pd
path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Uzio Emergeency Input File.xlsx"
try:
    df = pd.read_excel(path, header=1)
    print("Uzio Columns:")
    for c in df.columns:
        print(f"- {c}")
except Exception as e:
    print(e)
