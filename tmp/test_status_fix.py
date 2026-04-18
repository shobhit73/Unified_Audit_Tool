import pandas as pd
import sys
import os

# Add the project root to sys.path
sys.path.append(r'c:\Users\shobhit.sharma\Downloads\Deduction Tool')

from utils.audit_utils import validate_source_data

def test_status_validation():
    # Mock data
    data = {
        'Employee_Code': ['A1', 'A2', 'A3', 'A4'],
        'Employee_Status': ['Active', 'Terminated', 'Inactive', 'A04L'],
        'Termination_Date': ['', '01/01/2026', '', ''],
        'Legal_Firstname': ['John', 'Jane', 'Doe', 'Foo'],
        'Legal_Lastname': ['Smith', 'Doe', 'Smith', 'Bar'],
        'SS_Number': ['111223333', '222334444', '333445555', '444556666']
    }
    df = pd.DataFrame(data)
    
    # Resolved field map (matching what Paycom uses)
    resolved_field_map = {
        'Employee ID': 'Employee_Code',
        'Employment Status': 'Employee_Status',
        'Termination Date': 'Termination_Date',
        'First Name': 'Legal_Firstname',
        'Last Name': 'Legal_Lastname',
        'SSN': 'SS_Number'
    }
    
    result = validate_source_data(df, resolved_field_map)
    hard_errors = result['hard_errors']
    
    print("Validation Results:")
    for _, error in hard_errors.iterrows():
        print(f"ID: {error['Employee ID']}, Issue: {error['Issue']}")

    # Assertions
    # A1 (Active) should NOT have "Terminated/Inactive but missing Termination Date"
    a1_errors = hard_errors[hard_errors['Employee ID'] == 'A1']['Issue'].values
    if len(a1_errors) > 0:
        assert "Terminated/Inactive but missing Termination Date" not in a1_errors[0], "Error: Active employee flagged as missing termination date!"
    
    # A3 (Inactive) SHOULD have "Terminated/Inactive but missing Termination Date"
    a3_errors = hard_errors[hard_errors['Employee ID'] == 'A3']['Issue'].values
    assert len(a3_errors) > 0 and "Terminated/Inactive but missing Termination Date" in a3_errors[0], "Error: Inactive employee NOT flagged for missing termination date!"

    # A4 (A04L) should be flagged as Non-standard Status
    a4_errors = hard_errors[hard_errors['Employee ID'] == 'A4']['Issue'].values
    assert len(a4_errors) > 0 and "Non-standard Status" in a4_errors[0], "Error: Non-standard status NOT flagged!"

    print("\n✅ Test passed! The status validation logic is now correct.")

if __name__ == "__main__":
    test_status_validation()
