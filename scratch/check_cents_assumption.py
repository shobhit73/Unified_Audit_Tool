"""For the 5 mapped 'amount' fields, see whether UZIO values look like
cents (~ Paycom*100) or dollars (~ Paycom). Sample 20 employees."""
import pandas as pd

paycom = pd.read_csv(r"C:\Users\rohit.kaushik\Downloads\Chief Delivery\20260528004100_Advanced_Report_Writer_b4de73d1.csv", dtype=str)
uzio = pd.read_csv(r"C:\Users\rohit.kaushik\Downloads\Chief Delivery\Chief Delivery.csv", dtype=str)

PAIRS = [
    ("FIT_ADDL_WITHHOLDING_PER_PAY_PERIOD", "Fed_Addl_$"),
    ("FIT_DEDUCTIONS_OVER_STANDARD",        "Fed_Deductions_$"),
    ("FIT_CHILD_AND_DEPENDENT_TAX_CREDIT",  "Fed_Dependents_$"),
    ("FIT_OTHER_INCOME",                    "Fed_Other_Income_$"),
    ("SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD", "State_Addl_$"),
]

for uz_key, pc_col in PAIRS:
    print(f"\n=== {uz_key}  vs  {pc_col} ===")
    # Get UZIO non-zero values
    u_sub = uzio[(uzio["withholding_field_key"] == uz_key)
                 & (uzio["withholding_field_value"].astype(str).str.strip().isin(["0", "", "NaN"]) == False)]
    sample_emps = list(u_sub["employee_id"].head(10))
    if not sample_emps:
        print("  (no non-zero UZIO values for this field)")
        continue
    sub_u = u_sub.set_index("employee_id").loc[sample_emps][["state_code", "withholding_field_value"]]
    sub_p = paycom[paycom["Employee_Code"].isin(sample_emps)][["Employee_Code", pc_col]].set_index("Employee_Code")
    print(f"  {'emp':<10s} {'state':<6s} {'uzio_val':<12s} {'paycom_val':<12s} {'uz/100':<12s} {'matches dollars?':<18s}")
    for emp in sample_emps:
        uz_v = str(u_sub[u_sub["employee_id"] == emp].iloc[0]["withholding_field_value"])
        uz_state = str(u_sub[u_sub["employee_id"] == emp].iloc[0]["state_code"])
        pc_v = str(sub_p.loc[emp, pc_col]) if emp in sub_p.index else "(not in paycom)"
        try:
            uz_dollars = float(uz_v) / 100.0
            pc_dollars = float(pc_v)
            verdict = "OK (cents)" if abs(uz_dollars - pc_dollars) < 0.01 else (
                "OK (dollars)" if abs(float(uz_v) - pc_dollars) < 0.01 else "MISMATCH")
        except Exception:
            verdict = "(parse error)"
        print(f"  {emp:<10s} {uz_state:<6s} {uz_v:<12s} {pc_v:<12s} {uz_dollars:<12g} {verdict:<18s}")
