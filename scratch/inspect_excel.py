import pandas as pd

file_path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Prior Payroll Tool Dataset\Carvan\Prior Payroll Register Report_2026-05-01-04-12-15.xlsx"
xls = pd.ExcelFile(file_path)
print(f"Sheet names: {xls.sheet_names}")

for sheet in xls.sheet_names:
    print(f"\n--- Sheet: {sheet} ---")
    df = pd.read_excel(file_path, sheet_name=sheet, nrows=10)
    print(df.head(10))
