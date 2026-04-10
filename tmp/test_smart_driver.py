import pandas as pd
import sys
import os

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.audit_utils import validate_source_data

def test_smart_driver_logic():
    # 1. Mock Data
    data = {
        'Associate ID': ['E1', 'E2', 'E3', 'E4'],
        'Job Title Description': ['Driver', '', 'Manager', ''],
        'Department Description': ['Logistics', 'Driver', 'Admin', 'Driver'],
        'FLSA Description': ['', '', '', 'Non-Exempt'], # E4 already filled
        'Regular Pay Rate Description': ['Hourly', '', 'Salaried', 'Hourly']
    }
    df = pd.DataFrame(data)
    
    # 2. Resolved Field Map (ADP style)
    resolved_field_map = {
        'Employee ID': 'Associate ID',
        'Job Title': 'Job Title Description',
        'Department': 'Department Description',
        'FLSA Classification': 'FLSA Description',
        'Pay Type': 'Regular Pay Rate Description'
    }
    
    # 3. Test Detection
    print("--- Testing Detection ---")
    validation = validate_source_data(df, resolved_field_map)
    smart_fixes = validation['smart_driver_fixes']
    print(f"Smart Fixes Found: {len(smart_fixes)}")
    print(smart_fixes)
    
    # Check E1 (Existing Driver, Blank FLSA)
    assert any(smart_fixes['Employee ID'] == 'E1'), "E1 should be caught as Smart Driver fix"
    # Check E2 (Blank Job, Driver Dept, Blank FLSA)
    assert any(smart_fixes['Employee ID'] == 'E2'), "E2 should be caught as Smart Driver fix"
    # Check E3 (Manager, Blank FLSA) -> Should be in standard flsa_blanks, not smart_fixes
    assert not any(smart_fixes['Employee ID'] == 'E3'), "E3 should NOT be in smart_fixes"
    
    print("\n✅ Detection Test Passed!")

    # 4. Test Transformation (Simulation of Download Logic)
    print("\n--- Testing Transformation (Simulation) ---")
    df_fix = df.copy()
    fix_options = {'fix_driver_smart': True}
    
    c_jt = resolved_field_map['Job Title']
    c_dept = resolved_field_map['Department']
    c_flsa = resolved_field_map['FLSA Classification']
    
    # Logic from generator
    mask_jt_blank = df_fix[c_jt].isna() | (df_fix[c_jt].astype(str).str.strip().str.lower() == "nan") | (df_fix[c_jt].astype(str).str.strip() == "")
    mask_dept_driver = df_fix[c_dept].astype(str).str.lower().str.contains("driver", na=False)
    df_fix.loc[mask_jt_blank & mask_dept_driver, c_jt] = df_fix.loc[mask_jt_blank & mask_dept_driver, c_dept]
    
    mask_job_driver = df_fix[c_jt].astype(str).str.lower().str.contains("driver", na=False)
    mask_flsa_blank = df_fix[c_flsa].isna() | (df_fix[c_flsa].astype(str).str.strip().str.lower() == "nan") | (df_fix[c_flsa].astype(str).str.strip() == "")
    df_fix.loc[mask_job_driver & mask_flsa_blank, c_flsa] = "Non-Exempt"
    
    print("Transformed Data:")
    print(df_fix[[c_jt, c_flsa]])
    
    assert df_fix.loc[1, c_jt] == 'Driver', "E2 Job Title should be 'Driver'"
    assert df_fix.loc[0, c_flsa] == 'Non-Exempt', "E1 FLSA should be 'Non-Exempt'"
    assert df_fix.loc[1, c_flsa] == 'Non-Exempt', "E2 FLSA should be 'Non-Exempt'"
    assert df_fix.loc[2, c_flsa] == '', "E3 FLSA should remain blank (Manager)"
    
    print("\n✅ Transformation Test Passed!")

if __name__ == "__main__":
    test_smart_driver_logic()
