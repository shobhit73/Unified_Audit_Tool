import pandas as pd
import sys

try:
    xl = pd.ExcelFile(r'c:\Users\shobhit.sharma\Downloads\Deduction Tool\templates\Uzio_Census_Template.xlsm')
    print("Sheets:", xl.sheet_names)
    for sheet in xl.sheet_names:
        print(f"\nSheet: {sheet}")
        df = pd.read_excel(xl, sheet_name=sheet, nrows=10)
        print(df.head(5))
except Exception as e:
    print(f"Error: {e}")
