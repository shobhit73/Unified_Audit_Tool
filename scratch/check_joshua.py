import pandas as pd

file_path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Prior Payroll Tool Dataset\Carvan\Prior Payroll Register Report_2026-05-01-04-12-15.xlsx"
df = pd.read_excel(file_path, sheet_name="Prior Payroll Register", header=1)

# Look at Joshua Figueroa (0W5BRCOO3)
emp_id = "0W5BRCOO3"
emp_df = df[df['Employee ID'] == emp_id]
print(f"Data for {emp_id} (Joshua Figueroa):")
print(emp_df[['Employee ID', 'Pay Date', 'Gross Pay']])
