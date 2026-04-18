import pandas as pd
import sys
import traceback
sys.path.append(r'c:\Users\shobhit.sharma\Downloads\Deduction Tool')
from apps.adp.census_audit import run_comparison

with open('test_uzio.xlsx', 'rb') as f_uzio, open('test_adp.xlsx', 'rb') as f_adp:
    try:
        run_comparison(f_uzio, f_adp)
        print("Success! No exception raised.")
    except Exception as e:
        print("EXCEPTION RAISED:", type(e))
        traceback.print_exc()
