import pandas as pd
import sys
import os

# Add parent dir to path to import utils
sys.path.append(os.getcwd())

from utils.audit_utils import validate_source_data

def test_job_title_validation():
    data = {
        'Associate ID': ['1', '2', '3', '4'],
        'Legal First Name': ['John', 'Jane', 'Bob', 'Alice'],
        'Legal Last Name': ['Doe', 'Smith', 'Jones', 'Brown'],
        'Job Title Description': ['Manager', '', 'nan', None],
        'Department Description': ['Sales', 'Support', 'Tech', 'Admin'],
        'Tax ID (SSN)': ['111223333', '222334444', '333445555', '444556666']
    }
    df = pd.DataFrame(data)
    
    field_map = {
        'Employee ID': 'associate id',
        'Job Title': 'job title description',
        'Department': 'department description',
        'SSN': 'tax id (ssn)',
        'First Name': 'legal first name',
        'Last Name': 'legal last name'
    }
    
    # Normalize columns as the tool does
    df.columns = [c.lower() for c in df.columns]
    
    result = validate_source_data(df, field_map)
    hard_errors = result['hard_errors']
    
    print("Hard Errors found:")
    print(hard_errors)
    
    # Expecting IDs 2, 3, 4 to have errors
    error_ids = set(hard_errors['Employee ID'].tolist())
    expected_ids = {'2', '3', '4'}
    
    if expected_ids.issubset(error_ids):
        print("\n✅ SUCCESS: All blank/nan job titles were flagged.")
    else:
        print(f"\n❌ FAILURE: Missing flags for {expected_ids - error_ids}")

if __name__ == "__main__":
    test_job_title_validation()
