import pandas as pd
try:
    df = pd.read_excel(r'c:\Users\shobhit.sharma\Downloads\Deduction Tool\data\Paycom_Census_Mark_Logistics_24th_March_2026.xlsx', nrows=0)
    print('|'.join(df.columns.astype(str)))
except Exception as e:
    print(e)
