"""
Test: ADP Direct Deposit file compatibility with Selective Employee Extractor logic.
Checks:
1. File reads correctly as a flat table (no header offset)
2. ASSOCIATE ID column is detected correctly
3. Row filtering by IDs works as expected
4. Date (EFFECTIVE DATE) formats correctly to MM/DD/YYYY
"""
import pandas as pd
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.audit_utils import format_datetime_strings

FILE_PATH = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Sample Payment Data\Direct Deposit Information (7).xlsx"

print("=" * 60)
print("TEST: ADP Direct Deposit Extractor Compatibility")
print("=" * 60)

# Step 1: Read file
df = pd.read_excel(FILE_PATH, dtype=str)
print(f"\n[1] Rows: {len(df)}, Columns: {len(df.columns)}")
print(f"    Columns: {df.columns.tolist()}")

# Step 2: Detect ID column
DD_ID_COLUMN = 'ASSOCIATE ID'
assert DD_ID_COLUMN in df.columns, f"FAIL: '{DD_ID_COLUMN}' not found in headers!"
print(f"\n[2] ID Column Detected: '{DD_ID_COLUMN}' ✅")

# Step 3: Sample a few IDs and test filtering
sample_ids = df[DD_ID_COLUMN].dropna().unique()[:3].tolist()
print(f"\n[3] Sample IDs from file: {sample_ids}")
df_filtered = df[df[DD_ID_COLUMN].astype(str).str.strip().isin([s.strip() for s in sample_ids])].copy()
print(f"    Filtered rows for {len(sample_ids)} IDs: {len(df_filtered)} rows found ✅")
assert len(df_filtered) >= len(sample_ids), "FAIL: Not all IDs matched!"

# Note: One employee can have multiple rows (e.g. multiple bank accounts)
print(f"    (Note: Multiple rows per employee are expected for split deposits)")

# Step 4: Date formatting on EFFECTIVE DATE
print(f"\n[4] Raw EFFECTIVE DATE values: {df_filtered['EFFECTIVE DATE'].head(3).tolist()}")
df_filtered = format_datetime_strings(df_filtered, ['EFFECTIVE DATE'])
print(f"    Formatted EFFECTIVE DATE values: {df_filtered['EFFECTIVE DATE'].head(3).tolist()}")
for val in df_filtered['EFFECTIVE DATE'].tolist():
    if val and val.lower() not in ['', 'nan']:
        parts = val.split('/')
        assert len(parts) == 3 and len(parts[0]) == 2 and len(parts[2]) == 4, f"FAIL: Date '{val}' not in MM/DD/YYYY!"
print("    Date formatting: MM/DD/YYYY ✅")

print("\n" + "=" * 60)
print("ALL TESTS PASSED ✅")
print("=" * 60)
