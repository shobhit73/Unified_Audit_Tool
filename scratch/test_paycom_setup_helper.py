"""Smoke test the new Paycom Prior Payroll Setup Helper."""
import sys, os
sys.path.insert(0, r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\audit_fast_api")

from core.paycom.prior_payroll_setup_helper import run_paycom_prior_payroll_setup_helper


def run(label, prior_path, sched_path):
    with open(prior_path, "rb") as f:
        prior = f.read()
    with open(sched_path, "rb") as f:
        sched = f.read()
    results, xlsx_bytes = run_paycom_prior_payroll_setup_helper(
        prior, os.path.basename(prior_path),
        sched, os.path.basename(sched_path),
    )
    print(f"\n{'=' * 70}")
    print(f"{label}")
    print('=' * 70)
    for r in results["Summary"]:
        print(f"  {r['Metric']:42}  {r['Value']}")

    print("\n[1] What to Set Up")
    print(f"  Earnings ({len(results['Earnings_Codes'])}):")
    for r in results["Earnings_Codes"]:
        print(f"    {r['Type Code']:6} {r['Type Description']:35} ${r['Total $']:>12,}")
    print(f"  Contributions ({len(results['Contributions'])}):")
    for r in results["Contributions"]:
        print(f"    {r['Deduction Code']:6} {r['Deduction Desc']}")
    print(f"  Deductions ({len(results['Deductions'])}):")
    for r in results["Deductions"]:
        print(f"    {r['Deduction Code']:6} {r['Deduction Desc']}")

    print("\n[2] Pre-Tax vs Post-Tax")
    for r in results["Pre_Post_Tax"]:
        print(f"    {r['Code']:6} {r['Description']:32}  {r['Verdict']:10} {r['Flavor']}")

    print("\n[3] Bonus Verdict")
    b = results["Bonus"]
    print(f"  verdict: {b['verdict']}")
    print(f"  reason:  {b['reason']}")
    print(f"  bonus codes: {b.get('bonus_codes_found', [])}")
    if b.get("samples"):
        print(f"  samples: {b['samples'][:2]}")

    out_path = os.path.join(r"C:\Users\shobhit.sharma\Desktop\Audit Files",
                            f"_TEST_{label.replace(' ', '_')}.xlsx")
    with open(out_path, "wb") as f:
        f.write(xlsx_bytes)
    print(f"\n  Wrote test xlsx to: {out_path}")


run("Accelerated_Logistics",
    r"C:\Users\shobhit.sharma\Downloads\Accelerated Logistics Pior Payroll Setup\Accelerated Paycom Prior Payroll 04122026_04252026_05012026.csv",
    r"C:\Users\shobhit.sharma\Downloads\Accelerated Logistics Pior Payroll Setup\Paycom Accelerated Logistics Scheduled Deductions 27th April.xlsx")
