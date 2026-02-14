import pandas as pd
import os

file_path = os.path.join("Sample Data", "Multi_Client_East West Logistix_Employee_Census (2) (1).xlsm")

try:
    # Read row 3 (header) 
    df = pd.read_excel(file_path, sheet_name='Employee Details', header=3, nrows=0) 
    
    print("Searching for key columns...")
    
    key_terms = ["ID", "Status", "Hire", "Pay", "FLSA", "Salary", "Rate", "First", "Last", "SSN", "Social"]
    
    found_cols = {}
    for i, col in enumerate(df.columns):
        c_str = str(col).strip()
        for term in key_terms:
            if term.lower() in c_str.lower():
                found_cols.setdefault(term, []).append((i, c_str))

    for term, hits in found_cols.items():
        print(f"\n--- Matches for '{term}' ---")
        for idx, name in hits:
            print(f"  [{idx}] {name}")

except Exception as e:
    print(f"Error: {e}")
