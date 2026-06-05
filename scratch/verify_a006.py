import pandas as pd

paycom = pd.read_csv(r"C:\Users\rohit.kaushik\Downloads\Chief Delivery\20260528004100_Advanced_Report_Writer_b4de73d1.csv", dtype=str)
uzio = pd.read_csv(r"C:\Users\rohit.kaushik\Downloads\Chief Delivery\Chief Delivery.csv", dtype=str)

print("=== A006 in Paycom ===")
p = paycom[paycom["Employee_Code"] == "A006"]
print(f"  Fed_Dependents_$:   {p['Fed_Dependents_$'].iloc[0]!r}")
print(f"  Work_Location_State: {p['Work_Location_State'].iloc[0]!r}")
print(f"  State (home):       {p['State'].iloc[0]!r}")

print()
print("=== A006 in UZIO — all rows ===")
u = uzio[uzio["employee_id"] == "A006"]
print(f"  Total rows: {len(u)}")
fit = u[u["withholding_field_key"] == "FIT_CHILD_AND_DEPENDENT_TAX_CREDIT"]
print("  FIT_CHILD_AND_DEPENDENT_TAX_CREDIT rows:")
print(fit[["state_code", "tax_scope", "withholding_field_value", "effective_date"]].to_string(index=False))
print()
print("  Distinct field_keys for A006 in UZIO:")
print(sorted(u["withholding_field_key"].unique()))
