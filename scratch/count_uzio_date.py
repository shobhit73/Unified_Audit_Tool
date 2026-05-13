import pandas as pd

file_path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Prior Payroll Tool Dataset\Carvan\Prior Payroll Register Report_2026-05-01-04-12-15.xlsx"
df = pd.read_excel(file_path, sheet_name="Prior Payroll Register", header=1)

df_0501 = df[df['Pay Date'] == '05/01/2026']
print(f"Unique employees on 05/01/2026 in Uzio: {df_0501['Employee ID'].nunique()}")
