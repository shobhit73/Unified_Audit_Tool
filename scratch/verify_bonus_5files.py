"""Re-run the Paycom Prior Payroll Audit with all 5 Paycom files."""
import sys, io
sys.path.insert(0, r'c:\Users\rohit.kaushik\Downloads\Unified_Audit_Tool')

class _StreamlitStub:
    def __getattr__(self, name):
        def _noop(*a, **kw): return None
        return _noop
sys.modules['streamlit'] = _StreamlitStub()

from apps.paycom.total_comparison import run_comparison, load_mapping

PAYCOM_FILES = [
    r'C:\Users\rohit.kaushik\Downloads\Chief Delivery\payroll\PriorPayroll_12212025_03142026_03202026.csv',
    r'C:\Users\rohit.kaushik\Downloads\Chief Delivery\payroll\PriorPayroll_03152026_03282026_04032026.csv',
    r'C:\Users\rohit.kaushik\Downloads\Chief Delivery\payroll\PriorPayroll_03292026_04112026_04172026.csv',
    r'C:\Users\rohit.kaushik\Downloads\Chief Delivery\payroll\PriorPayroll_04122026_04252026_05012026.csv',
    r'C:\Users\rohit.kaushik\Downloads\Chief Delivery\payroll\PriorPayroll_04262026_05092026_05152026.csv',
]
UZIO = r'C:\Users\rohit.kaushik\Downloads\Chief Delivery\payroll\Prior Payroll Register Report_2026-06-01-05-38-22.xlsx'
EARN = r'C:\Users\rohit.kaushik\Downloads\Chief Delivery\payroll\Chief_Earnings_mapping.csv'

class FileLike(io.BytesIO):
    def __init__(self, path):
        with open(path, 'rb') as f:
            super().__init__(f.read())
        self.name = path

paycom_files = [FileLike(p) for p in PAYCOM_FILES]
uzio_file = FileLike(UZIO)
earn_file = FileLike(EARN)

mappings = load_mapping(earn_file, "Earnings", "Source Earning Code Name", "Uzio Earning Code Name")
print(f"Loaded {len(mappings)} earnings mappings")

res_df, emp_df, report_bytes, tax_df = run_comparison(paycom_files, uzio_file, mappings)

import pandas as pd
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 260)

print("\n=== Full Comparison (all 5 Paycom files) ===")
print(res_df.to_string())

print("\n=== Bonus row ===")
print(res_df[res_df['UZIO Item'] == 'Bonus'].to_string())
print("\n=== Bonus (Hours) row ===")
print(res_df[res_df['UZIO Item'] == 'Bonus (Hours)'].to_string())
print("\n=== Lookback bonus row ===")
print(res_df[res_df['UZIO Item'] == 'Lookback bonus'].to_string())

print("\n=== Employee Mismatches for Bonus ===")
if emp_df is not None and not emp_df.empty:
    b = emp_df[emp_df['UZIO Item'] == 'Bonus']
    print(f"Bonus mismatch rows: {len(b)}")
    if not b.empty:
        print(b.to_string())
    else:
        print("(none)")
else:
    print("(no employee mismatches)")
