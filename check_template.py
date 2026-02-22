# -*- coding: utf-8 -*-
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

file = r'c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Paycom Cenus Sample\Multi_Client_Pria Logistics_Employee_Census.xlsm'
xls = pd.ExcelFile(file, engine='openpyxl')
print("Sheets:", xls.sheet_names)
df = pd.read_excel(file, sheet_name='Employee Details', header=None, nrows=10)
print(df.head(10))
