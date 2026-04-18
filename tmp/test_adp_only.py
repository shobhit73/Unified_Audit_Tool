import pandas as pd
import sys
import traceback
sys.path.append(r'c:\Users\shobhit.sharma\Downloads\Deduction Tool')
from apps.adp.census_audit import deduplicate_adp, ADP_FIELD_MAP
from utils.audit_utils import norm_colname, norm_id, ensure_unique_columns

def test_process_adp():
    print("Reading test_adp.xlsx...")
    adp = pd.read_excel('test_adp.xlsx', dtype=str)
    
    adp = ensure_unique_columns(adp)
    adp.columns = [norm_colname(c) for c in adp.columns]
    
    ADP_KEY = norm_colname(ADP_FIELD_MAP.get('Employee ID', 'Associate ID'))
    print("ADP_KEY:", ADP_KEY)
    print("Columns available:", adp.columns.tolist()[:10]) # print first 10
    
    if ADP_KEY not in adp.columns:
         raise ValueError(f"Required column '{ADP_KEY}' not found in ADP file.")
    
    adp[ADP_KEY] = adp[ADP_KEY].astype(object).where(~adp[ADP_KEY].isna(), "").map(lambda v: str(v).strip().split(".")[0])
    
    print("Deduplicating...")
    adp = deduplicate_adp(adp, ADP_KEY)
    
    print("Normalizing IDs...")
    adp[ADP_KEY] = adp[ADP_KEY].apply(norm_id)
    
    print("Setting index...")
    adp_idx = adp.set_index(ADP_KEY, drop=False)
    
    print("Success! 'Associate ID' processed perfectly.")

try:
    test_process_adp()
except Exception as e:
    print("EXCEPTION RAISED:", type(e))
    traceback.print_exc()
