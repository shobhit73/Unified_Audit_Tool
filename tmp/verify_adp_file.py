import pandas as pd
import sys
import os

# Import the normalization and mapping functions
sys.path.append(os.getcwd())
try:
    from apps.adp.census_generator import ADP_FIELD_MAP, norm_colname
except ImportError:
    # Fallback if pathing is weird
    def norm_colname(c: str) -> str:
        import re
        if c is None: return ""
        c = str(c).replace("\n", " ").replace("\r", " ")
        c = c.replace("\u00A0", " ")
        c = c.replace("\u2019", "'").replace("\u201C", '"').replace("\u201D", '"')
        c = re.sub(r'\(.*?\)', '', c)
        c = re.sub(r"\s+", " ", c).strip()
        c = c.replace("*", "")
        c = c.strip('"').strip("'")
        return c.lower()
    ADP_FIELD_MAP = {
        'Zip': ['Primary Address: Zip / Postal Code'],
        'Mailing Zip': ['Legal / Preferred Address: Zip / Postal Code'],
        'Job Title': ['Job Title Description'],
        'Department': ['Department Description'],
        'Working Hours': ['Standard Hours']
    }

def test_adp_file(file_path):
    print(f"--- Testing File: {os.path.basename(file_path)} ---")
    
    try:
        # 1. Read the file
        df = pd.read_excel(file_path, dtype=str)
        print(f"Original Columns: {len(df.columns)}")
        
        # 2. Normalize columns
        original_columns = list(df.columns)
        norm_cols = [norm_colname(c) for c in df.columns]
        df.columns = norm_cols
        norm_to_orig = dict(zip(norm_cols, original_columns))
        
        # 3. Resolve field map
        resolved_field_map = {}
        # Using a subset of the map for testing
        test_map = {
            'Zip': ['Primary Address: Zip / Postal Code'],
            'Mailing Zip': ['Legal / Preferred Address: Zip / Postal Code'],
            'Job Title': ['Job Title Description'],
            'Department': ['Department Description'],
            'Working Hours': ['Standard Hours']
        }
        for std_name, vendor_cols in test_map.items():
            for vc in vendor_cols:
                nvc = norm_colname(vc)
                if nvc in df.columns:
                    resolved_field_map[std_name] = nvc
                    break
        
        print(f"Resolved Fields: {list(resolved_field_map.keys())}")
        
        # 4. Test Zip Fix Logic
        c_zip = resolved_field_map.get('Zip')
        print(f"\nZip Column detected: {c_zip} ('{norm_to_orig.get(c_zip, 'N/A')}')")
        
        if c_zip and c_zip in df.columns:
            def _fix_zip_local(z):
                if pd.isna(z) or str(z).strip() == "": return ""
                import re
                s = str(z).split('.')[0].split('-')[0]
                s = re.sub(r'[^0-9]', '', s)
                if not s: return ""
                if len(s) == 4: s = '0' + s
                return s[:5]
            
            zips = df[c_zip].dropna().unique()
            print(f"Unique Zips found: {len(zips)}")
            
            print("Zip Fix Samples:")
            samples = 0
            for z in zips:
                fixed = _fix_zip_local(z)
                if len(str(fixed)) == 5:
                    if len(str(z)) != 5 or '-' in str(z) or '.' in str(z) or str(z).startswith('0'):
                        print(f"  '{z}' -> '{fixed}'")
                        samples += 1
                if samples >= 10: break
            if samples == 0:
                print("  No irregular zips requiring fix found in top samples.")

        # 5. Test Standard Hours Fix
        c_sh = resolved_field_map.get('Working Hours')
        if c_sh:
            print(f"\nStandard Hours Column: {c_sh}")
            blanks = df[df[c_sh].isna() | (df[c_sh].astype(str).str.strip().lower() == "nan") | (df[c_sh].astype(str).str.strip() == "")]
            print(f"Blank Standard Hours found: {len(blanks)}")
            if len(blanks) > 0:
                print(f"  Standard Hours will be set to '0' for these {len(blanks)} rows.")

        print("\n--- Test Completed Successfully ---")

    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    file_path = r'c:\Users\shobhit.sharma\Downloads\Deduction Tool\data\Sample ADP Standard Census.xlsx'
    test_adp_file(file_path)
