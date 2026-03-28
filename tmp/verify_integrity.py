import pandas as pd
import os
import io

def verify_integrity():
    # Paths to sample files
    paycom_path = r'c:\Users\shobhit.sharma\Downloads\Deduction Tool\data\Paycom_Census_Mark_Logistics_24th_March_2026.xlsx'
    adp_path = r'c:\Users\shobhit.sharma\Downloads\Deduction Tool\data\Sample ADP Standard Census.xlsx'
    uzio_path = r'c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Census ADP Sample\Multi_Client_East West Logistix_Employee_Census (2) (1).xlsm'

    print("--- Verifying Paycom Integrity ---")
    df_pco = pd.read_excel(paycom_path, dtype=str)
    # Check for 00/00/0000
    has_zero_dates = df_pco.stack().str.contains('00/00/0000', na=False).any()
    print(f"Original Paycom has 00/00/0000: {has_zero_dates}")
    
    # Simulate cleaning
    df_pco_clean = df_pco.replace('00/00/0000', '')
    has_zero_dates_after = df_pco_clean.stack().str.contains('00/00/0000', na=False).any()
    print(f"Cleaned Paycom has 00/00/0000: {has_zero_dates_after}")

    print("\n--- Verifying ADP/Uzio Leading Zeros ---")
    # We want to ensure read_excel(..., dtype=str) preserves leading zeros
    # Example: SSN or Associate ID
    for path, name in [(adp_path, "ADP"), (uzio_path, "Uzio")]:
        header = 3 if "Uzio" in name else 0
        sheet = "Employee Details" if "Uzio" in name else 0
        df = pd.read_excel(path, dtype=str, sheet_name=sheet, header=header)
        
        # Look for a column that likely has leading zeros (e.g. SSN or IDs)
        id_col = 'Associate ID' if 'ADP' in name else ' Employee ID*'
        if id_col in df.columns:
            example_val = df[id_col].iloc[0]
            print(f"{name} {id_col} Example: '{example_val}' (Length: {len(str(example_val))})")

    print("\nVerification Complete.")

if __name__ == "__main__":
    verify_integrity()
