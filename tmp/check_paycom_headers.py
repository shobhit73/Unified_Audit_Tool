import pandas as pd
import sys
sys.stdout.reconfigure(encoding='utf-8')

uz_path = r"C:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Paycom Cenus Sample\Multi_Client_Pria Logistics_Employee_Census.xlsm"
pc_path = r"C:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Paycom Cenus Sample\Paycom_Census_Valuable_2802.xlsx"

print("-" * 70)
print(f"Reading Uzio headers from: {uz_path}")
try:
    uz_df = pd.read_excel(uz_path, sheet_name='Employee Details', header=3)
    print(f"Uzio columns found: {len(uz_df.columns)}")
    print(uz_df.columns.tolist())
except Exception as e:
    print(f"Failed to read Uzio: {e}")

print("\n" + "-" * 70)
print(f"Reading Paycom headers from: {pc_path}")
try:
    pc_df = pd.read_excel(pc_path)
    print(f"Paycom columns found: {len(pc_df.columns)}")
    print(pc_df.columns.tolist())
except Exception as e:
    print(f"Failed to read Paycom: {e}")
