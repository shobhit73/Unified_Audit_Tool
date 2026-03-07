import pandas as pd
import json

file_path = r"C:\Users\shobhit.sharma\Downloads\Deduction Tool\Prior Payroll Tool\ADP 61 degree North Prior Payroll History.xlsx"
xl = pd.ExcelFile(file_path)
sheet = xl.sheet_names[0]

# Read without assuming headers
df = xl.parse(sheet, header=None)

# Print first 15 rows as a list of lists (excluding NaNs to make it readable)
rows = []
for i in range(15):
    row_data = df.iloc[i].tolist()
    clean_row = [str(x) for x in row_data if pd.notna(x)]
    rows.append(f"Row {i}: {clean_row}")

print('\n'.join(rows))
