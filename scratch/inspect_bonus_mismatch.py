import pandas as pd

REPORT = r'C:\Users\rohit.kaushik\Downloads\Paycom_prior_payroll_audit_report.xlsx'
PAYCOM = r'C:\Users\rohit.kaushik\Downloads\Chief Delivery\payroll\PriorPayroll_12212025_03142026_03202026.csv'
UZIO = r'C:\Users\rohit.kaushik\Downloads\Chief Delivery\payroll\Prior Payroll Register Report_2026-06-01-05-38-22.xlsx'
MAP = r'C:\Users\rohit.kaushik\Downloads\Chief Delivery\payroll\Chief_Earnings_mapping.csv'

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 250)

# 1) Show the Full Comparison row for Bonus
print('=== FULL COMPARISON: Bonus row ===')
df_full = pd.read_excel(REPORT, sheet_name='Full Comparison')
print(df_full[df_full['UZIO Item'].str.contains('Bonus', case=False, na=False)].to_string())

print('\n=== EMPLOYEE MISMATCHES: Bonus rows ===')
df_emp = pd.read_excel(REPORT, sheet_name='Employee Mismatches')
b = df_emp[df_emp['UZIO Item'].str.contains('Bonus', case=False, na=False)]
print(f'Total Bonus mismatch rows: {len(b)}')
print(b.head(30).to_string())

# 2) Show the Earnings mapping
print('\n=== EARNINGS MAPPING (full) ===')
df_map = pd.read_csv(MAP)
print(df_map.to_string())

print('\n=== EARNINGS MAPPING — rows mentioning bonus ===')
mask = df_map.apply(lambda r: r.astype(str).str.contains('Bonus', case=False).any(), axis=1)
print(df_map[mask].to_string())
