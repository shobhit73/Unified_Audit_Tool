import pandas as pd
output_file = r'c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Sample Custom Reports\Falcon\Test Ouptut 1.xlsx'

# Read Census_Audit sheet
df = pd.read_excel(output_file, sheet_name='Census_Audit')
print("--- Census Audit Sample (First 5 rows) ---")
print(df.head())

# Check for empty values in Paycom Value column by Field
empty_summary = df[df['Paycom Value'].isna() | (df['Paycom Value'] == '')].groupby('Field').size()
print("\n--- Empty Paycom Values by Field ---")
print(empty_summary)

# Also check for 'nan' string if any
nan_str_summary = df[df['Paycom Value'].astype(str).str.lower() == 'nan'].groupby('Field').size()
print("\n--- 'NaN' Paycom Values by Field ---")
print(nan_str_summary)
