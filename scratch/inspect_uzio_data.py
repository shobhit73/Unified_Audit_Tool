import pandas as pd

file_path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Prior Payroll Tool Dataset\Carvan\Prior Payroll Register Report_2026-05-01-04-12-15.xlsx"
df = pd.read_excel(file_path, sheet_name="Prior Payroll Register", header=1)
print(f"Columns: {list(df.columns)}")

# Look at one employee
emp_id = "F3H56F8D0"
emp_df = df[df['Employee ID'] == emp_id]
print(f"\nData for {emp_id}:")
# Select some key columns to see if they repeat or differ
key_cols = ['Employee ID', 'Pay Date', 'Gross Pay', 'Net Pay', 'Federal Income Tax', 'Social Security Tax']
# Filter columns that exist
existing_cols = [c for c in key_cols if c in df.columns]
print(emp_df[existing_cols])
