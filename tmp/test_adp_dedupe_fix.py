import pandas as pd
import sys
import os

# Add the project root to sys.path
sys.path.append(r'c:\Users\shobhit.sharma\Downloads\Deduction Tool')

from apps.adp.census_audit import deduplicate_adp

def test_deduplicate_adp():
    # Mock data with duplicate Associate IDs
    data = {
        'Associate ID': ['A1', 'A1', 'A2'],
        'Position Status': ['Terminated', 'Active', 'Active'],
        'Legal First Name': ['John', 'John', 'Jane'],
        'Legal Last Name': ['Smith', 'Smith', 'Doe']
    }
    df = pd.DataFrame(data)
    
    key_col = 'Associate ID'
    
    print("Testing deduplicate_adp...")
    try:
        deduped = deduplicate_adp(df, key_col)
        
        print(f"Columns in deduped: {deduped.columns.tolist()}")
        
        # Check if key_col is in columns
        assert key_col in deduped.columns, f"Error: '{key_col}' column missing from results!"
        
        # Check if deduplication worked (should pick Active over Terminated for A1)
        a1_row = deduped[deduped[key_col] == 'A1']
        assert len(a1_row) == 1, "Error: A1 not deduplicated!"
        assert a1_row.iloc[0]['Position Status'] == 'Active', "Error: Did not correctly prioritize 'Active' status!"
        
        print("\n✅ Test passed! 'Associate ID' is preserved as a column.")
        
    except KeyError as e:
        print(f"\n❌ Test failed with KeyError: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_deduplicate_adp()
