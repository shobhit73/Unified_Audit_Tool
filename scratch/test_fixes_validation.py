import pandas as pd
import numpy as np
import io
import sys
import os

# Add the project root to sys.path so we can import from utils and core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'audit_fast_api')))

from utils.audit_utils import normalize_id, find_header_and_data
from core.census.sanity_check import generate_corrected_census_xlsx

def test_norm_id():
    print("Testing normalize_id...")
    assert normalize_id("0") == "0"
    assert normalize_id("000") == "0"
    assert normalize_id("123") == "123"
    assert normalize_id("00123") == "123"
    assert normalize_id(None) == ""
    print("normalize_id passed.")

def test_sanity_logic():
    print("Testing sanity logic (FLSA and Std Hours)...")
    data = {
        'Employee_Code': ['1', '2', '3', '4'],
        'Pay Type': ['Salary', 'Salaried', 'Hourly', 'Hour'],
        'FLSA Classification': ['', '', '', ''],
        'Working Hours': ['40', '40', '40', '40'],
        'DOL_Status': ['Active', 'Active', 'Active', 'Active']
    }
    df = pd.DataFrame(data)
    
    # Save to buffer
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    content = buffer.getvalue()
    
    # Run sanity
    field_map = {
        'FLSA Classification': 'FLSA Classification',
        'Pay Type': 'Pay Type',
        'Working Hours': 'Working Hours',
        'DOL_Status': 'DOL_Status'
    }
    fix_options = {'fix_flsa': True, 'fix_std_hours': True}
    
    corrected_bytes, summary = generate_corrected_census_xlsx(
        content, field_map, fix_options=fix_options, filename="test.xlsx"
    )
    
    df_result = pd.read_excel(io.BytesIO(corrected_bytes))
    
    # Check FLSA
    # Salary -> Exempt
    assert df_result.loc[0, 'FLSA Classification'] == 'Exempt'
    assert df_result.loc[1, 'FLSA Classification'] == 'Exempt'
    # Hourly -> Non-Exempt
    assert df_result.loc[2, 'FLSA Classification'] == 'Non-Exempt'
    assert df_result.loc[3, 'FLSA Classification'] == 'Non-Exempt'
    
    # Check Working Hours
    # Salary -> Should remain 40 (or whatever it was)
    assert str(df_result.loc[0, 'Working Hours']) == '40'
    # Hourly -> Should be 0
    assert str(df_result.loc[2, 'Working Hours']) == '0'
    assert str(df_result.loc[3, 'Working Hours']) == '0'
    
    print("sanity logic passed.")

def test_header_discovery():
    print("Testing find_header_and_data with Paycom-style junk...")
    csv_content = """Paycom Census Report
Some other junk line
Employee_Code,Name,Pay Type
1,Alice,Salary
2,Bob,Hourly
""".encode('utf-8')
    
    df, top, _ = find_header_and_data(csv_content, "test.csv")
    assert 'Employee_Code' in df.columns
    assert len(df) == 2
    print("find_header_and_data (CSV) passed.")

    # Excel-style junk
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        junk_df = pd.DataFrame([['Paycom Report'], ['']])
        junk_df.to_excel(writer, index=False, header=False, sheet_name='Sheet1')
        real_df = pd.DataFrame([['Employee_Code', 'Name'], ['1', 'Alice']])
        real_df.to_excel(writer, index=False, header=False, startrow=2, sheet_name='Sheet1')
    
    df, top, _ = find_header_and_data(buffer.getvalue(), "test.xlsx")
    assert 'Employee_Code' in df.columns
    print("find_header_and_data (Excel) passed.")

if __name__ == "__main__":
    try:
        test_norm_id()
        test_sanity_logic()
        test_header_discovery()
        print("\nALL TESTS PASSED!")
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
