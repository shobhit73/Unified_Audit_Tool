import pandas as pd

path = r"C:\Users\shobhit.sharma\Downloads\Job Titles.xlsx"
xl = pd.ExcelFile(path)
print("Sheets:", xl.sheet_names)
for s in xl.sheet_names:
    df = pd.read_excel(xl, s, dtype=str)
    print(f"\n--- {s} (rows={len(df)}, cols={list(df.columns)}) ---")
    print(df.head(20).to_string())
