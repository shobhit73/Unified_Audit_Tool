import pandas as pd
import os

# Using the file name from the user's screenshot
uzio_path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Multi_Client_East West Logistix_Employee_Census (2) (1).xlsm"

if os.path.exists(uzio_path):
    print(f"Reading: {uzio_path}")
    try:
        # audit_utils says header is row 4 (index 3)
        df = pd.read_excel(uzio_path, sheet_name='Employee Details', header=3)
        with open("uzio_headers.txt", "w") as f:
            for c in df.columns:
                f.write(f"{c}\n")
            
            f.write("\n--- Status Columns ---\n")
            cols = [c for c in df.columns if "Status" in str(c)]
            for c in cols:
                f.write(f"\nColumn: '{c}'\n")
                f.write(str(df[c].head().to_list()) + "\n")
        
        print("Headers written to uzio_headers.txt")
                
    except Exception as e:
        print(f"Error reading excel: {e}")
else:
    print(f"File not found: {uzio_path}")
