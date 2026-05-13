import sys
sys.path.append('c:/Users/shobhit.sharma/Downloads/Deduction Tool')
import pandas as pd
import io
from apps.adp.total_comparison import run_comparison
from utils.audit_utils import norm_colname

def load_mapping_csv(path, adp_col, uzio_col, cat_name):
    df = pd.read_csv(path)
    df.columns = [norm_colname(c) for c in df.columns]
    actual_adp = next((c for c in df.columns if adp_col.lower() in c.lower()), None)
    actual_uzio = next((c for c in df.columns if uzio_col.lower() in c.lower()), None)
    if not actual_adp or not actual_uzio:
        print(f'WARNING: Could not find columns in {cat_name}. Available: {df.columns.tolist()}')
        return []
    out = []
    for _, row in df.iterrows():
        a = str(row[actual_adp]).strip()
        u = str(row[actual_uzio]).strip()
        if a and u and a.lower() != 'nan' and u.lower() != 'nan':
            out.append({'Category': cat_name, 'ADP_Name': a, 'UZIO_Name': u})
    return out

all_mappings = []
all_mappings += load_mapping_csv(
    'c:/Users/shobhit.sharma/Downloads/Deduction Tool/Prior Payroll Tool Dataset/Travel Management Earning Mapping.csv',
    'Source Earning Code Name', 'Uzio Earning Code Name', 'Earnings')
all_mappings += load_mapping_csv(
    'c:/Users/shobhit.sharma/Downloads/Deduction Tool/Prior Payroll Tool Dataset/Travel Management Deduction Mapping final 2.csv',
    'Source Deduction Code Name', 'Uzio Deduction Code Name', 'Deductions')
all_mappings += load_mapping_csv(
    'c:/Users/shobhit.sharma/Downloads/Deduction Tool/Prior Payroll Tool Dataset/Travel Management Contribution Mapping.csv',
    'Source Contribution Code Name', 'Uzio Contribution Code Name', 'Contributions')
all_mappings += load_mapping_csv(
    'c:/Users/shobhit.sharma/Downloads/Deduction Tool/Prior Payroll Tool Dataset/travel_managment_tax_mapping_q1.csv',
    'Source Tax Code Name', 'Uzio Tax Code Description', 'Taxes')

print(f'Total mappings loaded: {len(all_mappings)}')

adp_files = [
    open('c:/Users/shobhit.sharma/Downloads/Deduction Tool/Prior Payroll Tool Dataset/Q1.csv', 'rb'),
    open('c:/Users/shobhit.sharma/Downloads/Deduction Tool/Prior Payroll Tool Dataset/Q2-April.csv', 'rb')
]
uzio_file = open('c:/Users/shobhit.sharma/Downloads/Deduction Tool/Prior Payroll Tool Dataset/Prior Payroll Register Report_2026-04-24-07-19-58.xlsx', 'rb')

res_df, excel_bytes = run_comparison(adp_files, uzio_file, all_mappings)

print('\n=== FULL COMPARISON ===')
print(res_df[['Category', 'UZIO Item', 'ADP Total', 'UZIO Total', 'Difference', 'Status']].to_string())

out_xls = pd.ExcelFile(io.BytesIO(excel_bytes))
print('\nSheets:', out_xls.sheet_names)

if 'Employee Mismatches' in out_xls.sheet_names:
    emp = out_xls.parse('Employee Mismatches')
    print('\n=== EMPLOYEE MISMATCHES ===')
    print(f'Total mismatches: {len(emp)}')
    print(emp.to_string())
else:
    print('\nNo Employee Mismatches tab (all match at per-employee level).')

# Save output
with open('c:/Users/shobhit.sharma/Downloads/Deduction Tool/Prior Payroll Tool Dataset/TEST_audit_output.xlsx', 'wb') as f:
    f.write(excel_bytes)
print('\nSaved to TEST_audit_output.xlsx')
