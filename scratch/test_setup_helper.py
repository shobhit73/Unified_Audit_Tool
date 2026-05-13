"""Smoke test the new ADP Prior Payroll Setup Helper on two real client files."""
import sys
sys.path.insert(0, r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\audit_fast_api")

from core.adp.prior_payroll_setup_helper import run_adp_prior_payroll_setup_helper

MASTER = r"C:\Users\shobhit.sharma\Downloads\State Tax Code.csv"
with open(MASTER, "rb") as f:
    master = f.read()


def run(label, path):
    with open(path, "rb") as f:
        content = f.read()
    print(f"\n=========== {label} ============")
    res, csv_bytes = run_adp_prior_payroll_setup_helper(
        content, adp_filename=path.split("\\")[-1], state_tax_master_content=master,
    )
    for row in res["Summary"]:
        print(f"  {row['Metric']:42}  {row['Value']}")

    print("\n  Earnings:")
    for r in res["Earnings_Codes"]:
        print(f"    {r['Code']:30} total=${r['Total $']:>12,}  emps={r['Employees']:>4}  hrs={r['Total Hours']}  rate={r['Avg Rate ($/hr)']}")

    print("\n  Contributions:")
    for r in res["Contributions"]:
        print(f"    {r['Code']:30} total=${r['Total $']:>10,}  emps={r['Employees']:>4}  verdict={r['Verdict']}  flavor={r['Pre-Tax Flavor']}  conf={r['Confidence']}")

    print("\n  Deductions:")
    for r in res["Deductions"]:
        print(f"    {r['Code']:30} total=${r['Total $']:>10,}  emps={r['Employees']:>4}  verdict={r['Verdict']:8}  flavor={r['Pre-Tax Flavor']:18}  conf={r['Confidence']}")

    print("\n  Taxes_Discovered:")
    for r in res["Taxes_Discovered"]:
        print(f"    {r['Source Column']:50} total=${r['Total $']:>12,}  emps={r['Employees']:>4}")

    print(f"\n  States: {[s['State'] for s in res['States_Detected']]}")
    print(f"  Tax_Mapping rows: {len(res['Tax_Mapping'])}")
    for r in res["Tax_Mapping"][:8]:
        print(f"    {r['Source Tax Code Name']:42}  {r['Uzio Tax Code']:8}  {r['Unique Tax ID']:35}  {r['Uzio Tax Code Description']}")
    if len(res["Tax_Mapping"]) > 8:
        print(f"    ... +{len(res['Tax_Mapping'])-8} more")

    if res["Tax_Mapping_Missing"]:
        print("\n  MISSING from master:")
        for m in res["Tax_Mapping_Missing"]:
            print(f"    {m}")

    print("\n  Bonus_Classification:")
    for r in res["Bonus_Classification"]:
        print(f"    {r}")
    print("\n  Bonus_Sample_Rows:")
    for s in res["Bonus_Sample_Rows"]:
        print(f"    {s}")


run("Carvan Q1 Consolidated",
    r"C:\Users\shobhit.sharma\Downloads\Carvan Prior Payroll Setup\Payroll_History_Q1_Consolidated.csv")

run("Travel Mgmt Q1",
    r"C:\Users\shobhit.sharma\Downloads\Travel Management Prior Payroll Setup\Q1.csv")
