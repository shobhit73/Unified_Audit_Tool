import pandas as pd
import sys
import os

def test_std_hours_fix():
    data = {
        'Standard Hours': ['40', '', 'nan', None]
    }
    df_download = pd.DataFrame(data)
    
    # Normalized column name
    c_sh = 'standard hours'
    df_download.columns = [c_sh]
    
    # Mock resolved_field_map and norm_to_orig
    resolved_field_map = {'Working Hours': c_sh}
    norm_to_orig = {c_sh: 'Standard Hours'}
    
    fix_options = {'fix_std_hours': True, 'rename_std_hours': True}
    
    # Apply logic from the PR
    if fix_options.get('fix_std_hours'):
        c_val = resolved_field_map.get('Working Hours')
        if c_val and c_val in df_download.columns:
            mask_sh = df_download[c_val].isna() | (df_download[c_val].astype(str).str.strip().lower() == "nan") | (df_download[c_val].astype(str).str.strip() == "")
            df_download.loc[mask_sh, c_val] = "0"
            
    if fix_options.get('rename_std_hours'):
        c_val = resolved_field_map.get('Working Hours')
        if c_val and c_val in norm_to_orig:
            norm_to_orig[c_val] = "Working hours per Week"
            
    # Final restoration
    restored_cols = [norm_to_orig.get(c, c) for c in df_download.columns]
    df_download.columns = restored_cols
    
    print("Processed DataFrame:")
    print(df_download)
    
    target_col = "Working hours per Week"
    if target_col in df_download.columns:
        actual_values = df_download[target_col].tolist()
        expected_values = ['40', '0', '0', '0']
        if actual_values == expected_values:
            print("\n✅ SUCCESS: Standard Hours fixed and column renamed correctly.")
        else:
            print(f"\n❌ FAILURE: Expected {expected_values}, got {actual_values}")
    else:
        print(f"\n❌ FAILURE: Column '{target_col}' not found.")

if __name__ == "__main__":
    test_std_hours_fix()
