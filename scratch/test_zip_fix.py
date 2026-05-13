import pandas as pd
import sys
import os
import io

# Add the project root to sys.path
sys.path.append(r"c:\Users\shobhit.sharma\Downloads\Deduction Tool")

from apps.adp.census_generator import preprocess_adp_file
from utils.audit_utils import generate_excel_with_audit

file_path = r"C:\Users\shobhit.sharma\Downloads\FASS Logistics\Census Report (1).csv"

with open(file_path, "rb") as f:
    data = f.read()
    file_obj = io.BytesIO(data)
    file_obj.name = "Census Report (1).csv"

    df_adp, original_columns, norm_to_orig, resolved_field_map = preprocess_adp_file(file_obj)

if df_adp is not None:
    c_zip = resolved_field_map.get('Zip')
    if c_zip:
        print(f"Zip column: {c_zip}")
        # Find 4 digit zips
        zips = df_adp[c_zip].astype(str).str.strip()
        four_digits = df_adp[zips.str.len() == 4]
        if not four_digits.empty:
            print(f"Found {len(four_digits)} rows with 4-digit zips.")
            print("Sample 4-digit zips:")
            print(four_digits[c_zip].head(10).tolist())
        else:
            print("No 4-digit zips found in source.")

        def _fix_zip_local(z):
            if pd.isna(z) or str(z).strip() == "": return ""
            import re
            s = str(z).split('.')[0].split('-')[0]
            s = re.sub(r'[^0-9]', '', s)
            if not s: return ""
            if len(s) == 4: s = '0' + s
            return s[:5]
        
        df_adp[c_zip] = df_adp[c_zip].apply(_fix_zip_local).astype(str)
        print("Sample Zips after fix (first 10):")
        print(df_adp[c_zip].head(10).tolist())
else:
    print("Pre-processing failed.")
