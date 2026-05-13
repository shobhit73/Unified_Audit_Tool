"""Verify the Streamlit setup helper module imports and analysis works."""
import sys, io
sys.path.insert(0, r"c:\Users\shobhit.sharma\Downloads\Deduction Tool")

# Bypass streamlit's runtime check by setting headless mode early
from apps.adp.prior_payroll_setup_helper import run_setup_helper

class Buf(io.BytesIO):
    """File-like with a .name attribute that streamlit's read_input_file expects."""
    def __init__(self, content, name):
        super().__init__(content)
        self.name = name

with open(r"C:\Users\shobhit.sharma\Downloads\State Tax Code.csv", "rb") as f:
    master_buf = Buf(f.read(), "State Tax Code.csv")

for label, p in [
    ("Carvan", r"C:\Users\shobhit.sharma\Downloads\Carvan Prior Payroll Setup\Payroll_History_Q1_Consolidated.csv"),
    ("Travel Mgmt", r"C:\Users\shobhit.sharma\Downloads\Travel Management Prior Payroll Setup\Q1.csv"),
]:
    with open(p, "rb") as f:
        adp_buf = Buf(f.read(), p.split("\\")[-1])
    master_buf.seek(0)
    res, csv_b = run_setup_helper(adp_buf, master_buf)
    print(f"\n=== {label} ===")
    for r in res["Summary"]:
        print(f"  {r['Metric']:42}  {r['Value']}")
    print(f"  Deductions verdicts:")
    for r in res["Deductions"]:
        print(f"    {r['Code']:25} {r['Verdict']:8} {r['Pre-Tax Flavor']}")
    print(f"  Tax mapping rows: {len(res['Tax_Mapping'])}")
