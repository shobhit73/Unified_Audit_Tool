import pandas as pd

# Files
adp_q2 = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Prior Payroll Tool Dataset\Carvan\Copy of Payroll History Q2.csv"
uzio_reg = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Prior Payroll Tool Dataset\Carvan\Prior Payroll Register Report_2026-05-01-04-12-15.xlsx"

emp_id = "VECRG6L2N"
date_check = "04/24/2026"

print(f"--- Investigation for {emp_id} on {date_check} ---")

# Check ADP Q2
df_adp = pd.read_csv(adp_q2)
df_adp_emp = df_adp[(df_adp['ASSOCIATE ID'] == emp_id) & (df_adp['PAY DATE'] == date_check)]
print(f"\nADP Entries ({len(df_adp_emp)} found):")
cols_to_show = ['NAME', 'PAY DATE', 'CHECK/VOUCHER NUMBER', 'GROSS PAY', 'REGULAR EARNINGS', 'SOCIAL SECURITY - EMPLOYEE TAX']
print(df_adp_emp[[c for c in cols_to_show if c in df_adp_emp.columns]])

# Check Uzio
df_uzio = pd.read_excel(uzio_reg, sheet_name="Prior Payroll Register", header=1)
df_uzio_emp = df_uzio[(df_uzio['Employee ID'] == emp_id) & (df_uzio['Pay Date'] == date_check)]
print(f"\nUzio Entries ({len(df_uzio_emp)} found):")
cols_u = ['Employee ID', 'Pay Date', 'Gross Pay', 'Regular Wage', 'Social Security Tax']
# Note: Uzio tax might be under a group header, but let's see what flat columns we have
print(df_uzio_emp[[c for c in cols_u if c in df_uzio_emp.columns]])
