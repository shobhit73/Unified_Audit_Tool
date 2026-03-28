import pandas as pd
import io
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from utils.audit_utils import check_duplicate_columns

def test_dupes():
    # 1. Test CSV with duplicates
    csv_content = "ID,Name,Name,Age\n1,John,Smith,30"
    csv_file = io.BytesIO(csv_content.encode('utf-8'))
    csv_file.name = "test.csv"
    
    dupes = check_duplicate_columns(csv_file)
    print(f"CSV Dupes found: {dupes}")
    
    # 2. Test Excel with duplicates
    df = pd.DataFrame([["ID", "Location", "Location", "Salary"]], columns=None)
    xlsx_file = io.BytesIO()
    df.to_excel(xlsx_file, index=False, header=False)
    xlsx_file.name = "test.xlsx"
    xlsx_file.seek(0)
    
    dupes_xlsx = check_duplicate_columns(xlsx_file)
    print(f"Excel Dupes found: {dupes_xlsx}")
    
    # 3. Test No Duplicates
    csv_clean = "ID,Name,Age\n1,John,30"
    csv_clean_file = io.BytesIO(csv_clean.encode('utf-8'))
    csv_clean_file.name = "clean.csv"
    
    dupes_clean = check_duplicate_columns(csv_clean_file)
    print(f"Clean CSV Dupes found: {dupes_clean}")

if __name__ == "__main__":
    test_dupes()
