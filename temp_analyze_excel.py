import pandas as pd
import sys

def analyze_excel(filepath, f_out):
    f_out.write(f"\n{'='*50}\n")
    f_out.write(f"ANALYZING: {filepath}\n")
    f_out.write(f"{'='*50}\n")
    try:
        xl = pd.ExcelFile(filepath)
        f_out.write(f"Sheets: {xl.sheet_names}\n\n")
        
        for sheet in xl.sheet_names:
            f_out.write(f"--- Sheet: {sheet} ---\n")
            df = pd.read_excel(filepath, sheet_name=sheet, nrows=5)
            f_out.write("Columns:\n")
            for col in df.columns:
                f_out.write(f"  - {col}\n")
            f_out.write("\nSample Data (first 2 rows):\n")
            f_out.write(df.head(2).to_string() + "\n\n")
    except Exception as e:
        f_out.write(f"Error reading {filepath}: {e}\n")

if __name__ == "__main__":
    files = [
        r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Sample Deduction Data\KDL LLC - Assigned Deductions Report_2026-01-31-02-31-20.xlsx",
        r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Sample Deduction Data\ADP Sample Files\Urban Box - Voluntary Deduction.xlsx",
        r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Sample Deduction Data\Master Mapping for Deductions.xlsx"
    ]
    with open(r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\excel_structure.txt", "w", encoding="utf-8") as f_out:
        for f in files:
            analyze_excel(f, f_out)
