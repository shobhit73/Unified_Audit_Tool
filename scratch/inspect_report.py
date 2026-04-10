import pandas as pd

file_path = r"c:\Users\rohit.kaushik\Downloads\Unified Audit Tool\Prior payroll audit report (3).xlsx"
try:
    # Read the 3rd sheet (Employee Mismatches)
    df = pd.read_excel(file_path, sheet_name="Employee Mismatches")
    print("Column names in Employee Mismatches:")
    print(df.columns.tolist())
    print("\nFirst 10 rows:")
    print(df.head(10).to_string(index=False))
except Exception as e:
    print(f"Error reading Excel: {e}")
