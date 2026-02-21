import pandas as pd
import sys

def analyze_paycom_file(filepath, f_out):
    f_out.write(f"\n{'='*50}\n")
    f_out.write(f"ANALYZING: {filepath}\n")
    f_out.write(f"{'='*50}\n")
    try:
        xls = pd.ExcelFile(filepath)
        f_out.write(f"Sheets: {xls.sheet_names}\n\n")
        
        for sheet in xls.sheet_names:
            f_out.write(f"--- Sheet: {sheet} ---\n")
            df = pd.read_excel(xls, sheet_name=sheet, header=None, nrows=20)
            f_out.write("First 20 rows:\n")
            f_out.write(df.to_string() + "\n\n")
            
    except Exception as e:
        f_out.write(f"Error reading {filepath}: {e}\n")

if __name__ == "__main__":
    files = [
        r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Sample Deduction Data\Paycom Deduction Data\Pria Assigned Deductions Report_2026-02-13-07-37-22-1 (1).xlsx"
    ]
    with open(r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\paycom_structure.txt", "w", encoding="utf-8") as f_out:
        for f in files:
            analyze_paycom_file(f, f_out)
