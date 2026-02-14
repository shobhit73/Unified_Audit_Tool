import pandas as pd

path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Paycom Cenus Sample\Pria Paycom Cenus.xlsx"

print(f"Reading: {path}")
df = pd.read_excel(path)

# Find Angie (Emp Code 1)
# Column might be 'Employee_Code'
col_id = next((c for c in df.columns if "Employee_Code" in c), None)

if col_id:
    print(f"ID Column: {col_id}")
    # Filter for ID 1
    row = df[df[col_id] == 1]
    if not row.empty:
        print("\nRow for Employee_Code == 1:")
        # Print all columns that have values (drop NaNs for clarity)
        r = row.iloc[0].dropna()
        for k, v in r.items():
            print(f"{k}: {v}")
            
        print("\n--- Checking for Net/Dist columns explicitly ---")
        param_cols = [c for c in df.columns if "Net_" in c or "Dist_" in c]
        for c in param_cols:
            val = row.iloc[0].get(c)
            print(f"{c}: {val}")
    else:
        print("Employee 1 not found via integer match. Trying string '1'...")
        row = df[df[col_id].astype(str).str.strip() == "1"]
        if not row.empty:
             print("Found via string match.")
else:
    print("Employee_Code column not found.")
