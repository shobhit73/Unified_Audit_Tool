import pandas as pd
import numpy as np
from utils.audit_utils import selective_update_uzio

def test_selective_update_with_duplicates():
    # 1. Mock Source Data with Duplicates
    df_source = pd.DataFrame({
        'Associate ID': ['EMP001', 'EMP001', 'EMP002'], # Duplicate EMP001
        'Job Title Description': ['Dispatcher', 'Driver', 'Manager'],
        'Work Location Description': ['DCH6', 'DCH6', 'NYC']
    })
    
    vendor_map = {
        'Employee ID': 'Associate ID',
        'Job Title': 'Job Title Description',
        'Work Location': 'Work Location Description'
    }
    
    # 2. Mock Uzio Template
    df_template = pd.DataFrame({
        'Employee ID*': ['EMP001', 'EMP002'],
        'Job Title': ['Old Job 1', 'Old Job 2'],
        'Work Location': ['Old Loc 1', 'Old Loc 2'],
        'Employee SSN': ['1111', '2222']
    })
    
    selected_cols = ['Job Title']
    
    print("Testing selective_update_uzio with duplicate Employee IDs in source...")
    try:
        df_result, summary, df_changes = selective_update_uzio(df_source, df_template, selected_cols, vendor_map)
        print("Summary: " + str(summary))
        
        # Verify it picked the FIRST and didn't crash
        assert df_result.iloc[0]['Job Title'] == 'Dispatcher' # First occurrence
        print("\nSUCCESS: Deduplication successful - no crash and correct data picked!")
        
    except ValueError as e:
        print("\nFAILED: " + str(e))
        exit(1)
    except Exception as e:
        print("\nUNEXPECTED ERROR: " + str(e))
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    test_selective_update_with_duplicates()
