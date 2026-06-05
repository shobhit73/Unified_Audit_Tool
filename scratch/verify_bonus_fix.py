"""End-to-end re-run of the Paycom Prior Payroll Audit on the same inputs,
confirming the Bonus row is now a Match."""
import sys, io
sys.path.insert(0, r'c:\Users\rohit.kaushik\Downloads\Unified_Audit_Tool')

# Stub streamlit so we can import the module without a UI
class _StreamlitStub:
    def __getattr__(self, name):
        def _noop(*a, **kw): return None
        return _noop
sys.modules['streamlit'] = _StreamlitStub()

from apps.paycom.total_comparison import run_comparison, load_mapping

PAYCOM = r'C:\Users\rohit.kaushik\Downloads\Chief Delivery\payroll\PriorPayroll_12212025_03142026_03202026.csv'
UZIO   = r'C:\Users\rohit.kaushik\Downloads\Chief Delivery\payroll\Prior Payroll Register Report_2026-06-01-05-38-22.xlsx'
EARN   = r'C:\Users\rohit.kaushik\Downloads\Chief Delivery\payroll\Chief_Earnings_mapping.csv'

class FileLike(io.BytesIO):
    def __init__(self, path):
        with open(path, 'rb') as f:
            super().__init__(f.read())
        self.name = path

paycom_files = [FileLike(PAYCOM)]
uzio_file = FileLike(UZIO)
earn_file = FileLike(EARN)

mappings = load_mapping(earn_file, "Earnings", "Source Earning Code Name", "Uzio Earning Code Name")
print(f"Loaded {len(mappings)} earnings mappings")

res_df, emp_df, _, _ = run_comparison(paycom_files, uzio_file, mappings)

print("\n=== Full Comparison (post-fix) ===")
import pandas as pd
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 250)
print(res_df.to_string())

print("\n=== Bonus row ===")
print(res_df[res_df['UZIO Item'] == 'Bonus'].to_string())
print("\n=== Bonus (Hours) row ===")
print(res_df[res_df['UZIO Item'] == 'Bonus (Hours)'].to_string())

print("\n=== Employee Mismatches with Bonus item ===")
if emp_df is not None and not emp_df.empty:
    b = emp_df[emp_df['UZIO Item'] == 'Bonus']
    print(f"Bonus rows in Employee Mismatches: {len(b)}")
    if not b.empty:
        print(b.head(15).to_string())
else:
    print("(no employee mismatches at all)")
