import pandas as pd
import sys
sys.stdout.reconfigure(encoding='utf-8')

uz_path = r"C:\Users\shobhit.sharma\Downloads\JM Parcel\Multi_Client_JM Parcel Service LLC_Employee_Census.xlsm"
adp_path = r"C:\Users\shobhit.sharma\Downloads\JM Parcel\ADP JM Parcel Employee Census 26th March.xlsx"

print("-" * 70)
print(f"Reading Uzio headers from: {uz_path}")
try:
    # Read Excel - header=3 means 4th row is header (Row 4 in Excel)
    uz_df = pd.read_excel(uz_path, sheet_name='Employee Details', header=3)
    print(f"Uzio columns found: {len(uz_df.columns)}")
    print(uz_df.columns.tolist())
except Exception as e:
    print(f"Failed to read Uzio: {e}")

print("\n" + "-" * 70)
print(f"Reading ADP headers from: {adp_path}")
try:
    adp_df = pd.read_excel(adp_path)
    print(f"ADP columns found: {len(adp_df.columns)}")
    print(adp_df.columns.tolist())
except Exception as e:
    print(f"Failed to read ADP: {e}")
