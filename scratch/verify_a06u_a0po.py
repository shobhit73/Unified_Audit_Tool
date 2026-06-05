"""Trace what happens for A06U and A0PO after the fix."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from apps.paycom.withholding_audit import _pivot_uzio_long_to_wide

paycom = pd.read_csv(r"C:\Users\rohit.kaushik\Downloads\Chief Delivery\20260528004100_Advanced_Report_Writer_b4de73d1.csv", dtype=str)
uzio = pd.read_csv(r"C:\Users\rohit.kaushik\Downloads\Chief Delivery\Chief Delivery.csv", dtype=str)

fed, state = _pivot_uzio_long_to_wide(uzio)
sw_idx = state.set_index(["employee_id", "state_code"])

for emp in ["A06U", "A0PO"]:
    print(f"\n=== {emp} ===")
    p = paycom[paycom["Employee_Code"] == emp].iloc[0]
    work_state = str(p.get("Work_Location_State", "")).upper()
    paycom_addl = p.get("State_Addl_$", "")
    print(f"  Paycom Work_Location_State: {work_state!r}")
    print(f"  Paycom State_Addl_$:        {paycom_addl!r}")
    # SIT match
    key = (emp, work_state)
    if key in sw_idx.index:
        uz_addl = sw_idx.loc[key, "SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD"]
        print(f"  UZIO SIT_ADDL ({work_state}):  {uz_addl!r}")
        try:
            print(f"  UZIO/100 = ${float(uz_addl)/100:.2f}   vs Paycom = ${float(paycom_addl):.2f}")
            print(f"  Match: {abs(float(uz_addl)/100 - float(paycom_addl)) < 0.01}")
        except Exception as e:
            print(f"  parse error: {e}")
    else:
        print(f"  No UZIO state record for ({emp}, {work_state})")
