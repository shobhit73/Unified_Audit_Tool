"""Verify the simplified-UI helpers produce sensible plain-English output."""
import sys, io
sys.path.insert(0, r"c:\Users\shobhit.sharma\Downloads\Deduction Tool")

from apps.adp.prior_payroll_setup_helper import (
    run_setup_helper, _pick_bonus_example, _deduction_reason,
)


class Buf(io.BytesIO):
    def __init__(self, c, name):
        super().__init__(c); self.name = name


with open(r"C:\Users\shobhit.sharma\Downloads\State Tax Code.csv", "rb") as f:
    master = Buf(f.read(), "State Tax Code.csv")

for label, p in [
    ("Carvan", r"C:\Users\shobhit.sharma\Downloads\Carvan Prior Payroll Setup\Payroll_History_Q1_Consolidated.csv"),
    ("TravelMgmt", r"C:\Users\shobhit.sharma\Downloads\Travel Management Prior Payroll Setup\Q1.csv"),
]:
    with open(p, "rb") as f:
        adp = Buf(f.read(), p.split("\\")[-1])
    master.seek(0)
    res, _ = run_setup_helper(adp, master)

    print(f"\n========== {label} ==========")
    print("\n[1] WHAT TO SET UP")
    print("  Earnings:    ", [r["Code"] for r in res["Earnings_Codes"]])
    print("  Contributions:", [r["Code"] for r in res["Contributions"]])
    print("  Deductions:  ", [r["Code"] for r in res["Deductions"]])

    print("\n[2] BONUS")
    bonus = res["Bonus_Classification"][0]
    sample = _pick_bonus_example(res["Bonus_Sample_Rows"], bonus["Verdict"])
    print(f"  Verdict: {bonus['Verdict']}")
    if sample:
        print(f"  Example: {sample['associate']}  rr={sample['regular_rate']}  exp_ot={sample['expected_ot_rate_1.5x']}  actual_ot={sample['actual_ot_rate']}  diff={sample['diff_pct']}%")

    print("\n[3] DEDUCTIONS PRE/POST")
    for r in res["Contributions"] + res["Deductions"]:
        v = "PRE-TAX" if r["Verdict"] == "pre_tax" else "POST-TAX"
        why = _deduction_reason(r)
        print(f"  {r['Code']:25} {v:9}  {why[:120]}")
