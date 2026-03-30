import pandas as pd
import sys
import os

# Import the normalization and mapping functions
sys.path.append(os.getcwd())
from apps.paycom.census_generator import PAYCOM_FIELD_MAP, norm_colname

def test_census_file(file_path):
    print(f"--- Testing File: {os.path.basename(file_path)} ---")
    
    try:
        # 1. Read the file
        if file_path.endswith('.xlsx'):
            df = pd.read_excel(file_path, dtype=str)
        else:
            df = pd.read_csv(file_path, dtype=str)
        
        print(f"Original Columns: {len(df.columns)}")
        
        # 2. Normalize columns
        original_columns = list(df.columns)
        norm_cols = [norm_colname(c) for c in df.columns]
        df.columns = norm_cols
        norm_to_orig = dict(zip(norm_cols, original_columns))
        
        # 3. Resolve field map
        resolved_field_map = {}
        for std_name, vendor_cols in PAYCOM_FIELD_MAP.items():
            for vc in vendor_cols:
                nvc = norm_colname(vc)
                if nvc in df.columns:
                    resolved_field_map[std_name] = nvc
                    break
        
        print(f"Resolved Fields: {len(resolved_field_map)} / {len(PAYCOM_FIELD_MAP)}")
        
        # 4. Test Zip Fix Logic
        c_zip = resolved_field_map.get('Zip')
        print(f"Zip Column detected: {c_zip} ('{norm_to_orig.get(c_zip, 'N/A')}')")
        
        if c_zip and c_zip in df.columns:
            def _fix_zip_local(z):
                if pd.isna(z) or str(z).strip() == "": return ""
                import re
                s = str(z).split('.')[0].split('-')[0]
                s = re.sub(r'[^0-9]', '', s)
                if not s: return ""
                if len(s) == 4: s = '0' + s
                return s[:5]
            
            # Sample some problematic zips if any
            zips = df[c_zip].dropna().unique()
            print(f"Unique Zips found: {len(zips)}")
            
            print("\nZip Fix Samples:")
            samples = 0
            for z in zips:
                fixed = _fix_zip_local(z)
                if len(str(z)) != 5 or '-' in str(z) or '.' in str(z):
                    print(f"  '{z}' -> '{fixed}'")
                    samples += 1
                if samples >= 10: break
            if samples == 0:
                print("  No irregular zips found in first few unique values.")

        # 5. Test Position Fix Logic
        c_job = resolved_field_map.get('Job Title')
        c_dep = resolved_field_map.get('Department')
        print(f"\nJob Title Column: {c_job} ('{norm_to_orig.get(c_job, 'N/A')}')")
        print(f"Department Column: {c_dep} ('{norm_to_orig.get(c_dep, 'N/A')}')")
        
        if c_job and c_dep:
            blanks = df[df[c_job].isna() | (df[c_job].astype(str).str.strip().lower() == "nan") | (df[c_job].astype(str).str.strip() == "")]
            print(f"Blank Job Titles found: {len(blanks)}")
            if len(blanks) > 0:
                print("Position Fix Samples:")
                for i, row in blanks.head(5).iterrows():
                    print(f"  Row {i}: Dept '{row[c_dep]}' -> Job Title will be '{row[c_dep]}'")
        
        print("\n--- Test Completed Successfully ---")

    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    file_path = r'c:\Users\shobhit.sharma\Downloads\Deduction Tool\data\Paycom_Census_Mark_Logistics_24th_March_2026.xlsx'
    test_census_file(file_path)
