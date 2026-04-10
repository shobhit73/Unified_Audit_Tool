
import pandas as pd
import sys
import os

# Add the root directory to path so we can import utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.audit_utils import get_identity_match_map, norm_ssn_canonical, detect_duplicate_ssns

def test_identity_matching():
    print("Testing Identity Matching Logic...")

    # 1. Mock Uzio Data
    uzio_data = {
        'Employee ID': ['742-64-5030', '100', '101'],
        'First Name': ['Santiago', 'John', 'Jane'],
        'Last Name': ['Valencia Bedoya', 'Doe', 'Smith'],
        'SSN': ['645-30-1234', '111-22-3333', '999-88-7777'],
        'Date of Birth': ['01/01/1990', '02/02/1980', '03/03/1970']
    }
    df_uzio = pd.DataFrame(uzio_data)

    # 2. Mock Vendor Data (ADP/Paycom)
    # Santiago has a DIFFERENT ID here (792- instead of 742-)
    vendor_data = {
        'ID': ['792-64-5030', '100', '999'], # 999 is vendor-only
        'SSN': ['645301234', '111223333', '000112222'], # No dashes here
        'First Name': ['Santiago', 'John', 'New'],
        'Last Name': ['Valencia Bedoya', 'Doe', 'Employee']
    }
    df_vendor = pd.DataFrame(vendor_data)

    print("\nRunning get_identity_match_map...")
    match_map = get_identity_match_map(
        df_uzio, df_vendor,
        uzio_id_col='Employee ID',
        vendor_id_col='ID',
        uzio_ssn_col='SSN',
        vendor_ssn_col='SSN'
    )

    print(f"Match Map Results: {match_map}")

    # Assertions
    # Santiago should be matched despite ID mismatch
    assert match_map.get('742-64-5030') == '792-64-5030', f"Failed to match Santiago! Got {match_map.get('742-64-5030')}"
    
    # John Doe (100) is a direct match, so he won't be in the correction map
    assert match_map.get('100') is None, "John Doe should not be in the map (direct ID match)"
    
    # Jane Smith (101) is not in vendor
    assert '101' not in match_map or match_map['101'] is None, "Jane Smith should not have a match!"

    print("\n✅ Identity matching tests passed!")

def test_duplicate_ssn_detection():
    print("\nTesting Duplicate SSN Detection...")
    df_dupes = pd.DataFrame({
        'ID': ['1', '2', '3', '4'],
        'SSN': ['111223333', '111223333', '999887777', ''] # 1 & 2 have same SSN
    })
    dupes = detect_duplicate_ssns(df_dupes, 'ID', 'SSN')
    print(f"Duplicate SSNs found: {dupes}")
    
    assert '111223333' in dupes
    assert len(dupes['111223333']) == 2
    assert '1' in dupes['111223333']
    assert '2' in dupes['111223333']
    assert '999887777' not in dupes
    
    print("✅ Duplicate SSN detection test passed!")

if __name__ == "__main__":
    test_identity_matching()
    test_duplicate_ssn_detection()
