import pandas as pd
import os

file_path = r'C:\Users\rohit.kaushik\Downloads\Unified Audit Tool\Prior Payroll Register Report_2026-04-02-04-06-15.xlsx'

if os.path.exists(file_path):
    xls = pd.ExcelFile(file_path)
    df_peek = pd.read_excel(xls, sheet_name='Prior Payroll Register', header=None, nrows=10)
    print(df_peek.iloc[0:2, 10:40]) # Check a range of columns
