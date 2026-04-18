import pandas as pd
import sys
sys.path.append(r'c:\Users\shobhit.sharma\Downloads\Deduction Tool')
from apps.adp.census_audit import deduplicate_adp

data={'Associate ID': ['A1', 'A2', 'A3'], 'Position Status': ['Terminated', 'Active', 'Active']}
df=pd.DataFrame(data)
key_col='Associate ID'
try:
    deduped=deduplicate_adp(df, key_col)
    print("SUCCESS")
    print(deduped.columns.tolist())
except Exception as e:
    import traceback
    traceback.print_exc()
