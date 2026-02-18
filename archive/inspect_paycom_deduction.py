import pandas as pd
import io

# Paths provided by user
uzio_path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Sample Deduction Data\Paycom Deduction Data\Pria Assigned Deductions Report_2026-02-13-07-37-22-1 (1).xlsx"
paycom_path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Sample Deduction Data\Paycom Deduction Data\Pria Paycom Scheduled Deduction Report.csv"

print("--- Inspecting Uzio Deduction File ---")
try:
    # Try header=0 and header=1 just in case
    df_u = pd.read_excel(uzio_path, header=0)
    print("Header=0 Columns:", list(df_u.columns))
    print(df_u.head(3).to_string())
except Exception as e:
    print(f"Error reading Uzio: {e}")

print("\n--- Inspecting Paycom Deduction File ---")
try:
    # Paycom is CSV
    df_p = pd.read_csv(paycom_path)
    print("Columns:", list(df_p.columns))
    print(df_p.head(3).to_string())
except Exception as e:
    print(f"Error reading Paycom: {e}")
