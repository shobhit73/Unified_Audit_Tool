import os
import sys
import pandas as pd
from datetime import datetime

# Adjust path to find local modules
sys.path.append(os.getcwd())

try:
    from census_audit_app import run_comparison as run_adp
    from paycom_census_audit_app import run_comparison as run_paycom
    from audit_utils import UZIO_RAW_MAPPING
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

def create_mock_uzio_file(adp_id):
    print(f"Creating mock Uzio file for matching Employee ID: {adp_id}")
    # Create a DataFrame matching the 'Employee Details' sheet structure
    # Header at row 4 (index 3).
    # Columns must match keys in UZIO_RAW_MAPPING
    
    # Invert mapping to get Raw Columns
    raw_cols = list(UZIO_RAW_MAPPING.keys())
    
    data = {c: [] for c in raw_cols}
    
    # Add one matching row
    data['Employee ID*'].append(adp_id)
    data['Employee First Name*'].append("TestFirst")
    data['Employee Last Name*'].append("TestLast")
    data['Employment Status*'].append("Active")
    data['Pay Type*'].append("Salaried")
    data['Annual Salary(Digits)**'].append("100000")
    # Fill others with empty
    for c in raw_cols:
        if c not in data or not data[c]:
            data[c].append("")
            
    df = pd.DataFrame(data)
    
    # Write to Excel with specific sheet and header position
    mock_path = os.path.join("Sample Data", "Mock_Uzio_Raw.xlsx")
    with pd.ExcelWriter(mock_path, engine='openpyxl') as writer:
        # Write 3 empty rows then header
        df.to_excel(writer, sheet_name='Employee Details', startrow=3, index=False)
        
    print(f"Created {mock_path}")
    return mock_path

def test_audit_tools():
    print("\n--- Testing Audit Tools ---")
    
    # 1. Identify ADP Sample
    adp_path = os.path.join("Sample Data", "ADP Cenus File.xlsx")
    paycom_path = os.path.join("Sample Data", "Paycom Cenus File.csv")
    
    if not os.path.exists(adp_path):
        print("ADP Sample not found.")
        return

    # Read ADP to get an ID
    try:
        adp_df = pd.read_excel(adp_path)
        # Assuming col 1 is Associate ID based on inspection
        # 0: Legal First Name, 1: Associate ID
        sample_id = adp_df.iloc[0, 1] 
        print(f"Found Sample ADP ID: {sample_id}")
    except Exception as e:
        print(f"Error reading ADP for mock data: {e}")
        sample_id = "12345"

    # 2. Create Mock Uzio
    uzio_path = create_mock_uzio_file(sample_id)
    
    # 3. Test ADP Tool
    print("\n[Test] Running ADP Audit...")
    try:
        # Load files as bytes to simulate streamlit upload if needed, 
        # BUT run_comparison now accepts file paths directly via pd.read_excel/read_utils?
        # Utils uses pd.ExcelFile(file) which accepts path.
        # Apps use uploaded_file.getvalue() (bytes).
        # Utils 'read_uzio_raw_file' handles bytes or path?
        # It initiates pd.ExcelFile(file).
        # So passing path string should work.
        
        # However, ADP app `run_comparison` expects `uzio_file` and `adp_file`.
        # And then calls `read_uzio_raw_file(uzio_file)`.
        # And `pd.read_excel(adp_file)`.
        # Passing paths directly should work for pandas.
        
        # Test ADP
        res = run_adp(uzio_path, adp_path)
        print("ADP Audit Success! Output bytes length:", len(res))
        
        # Save output
        with open("verification_output/ADP_Audit_Test.xlsx", "wb") as f:
            f.write(res)
            
    except Exception as e:
        print(f"ADP Audit Failed: {e}")
        import traceback
        traceback.print_exc()

    # 4. Test Paycom Tool
    print("\n[Test] Running Paycom Audit...")
    if os.path.exists(paycom_path):
        try:
            # Paycom file might be .csv
            # Paycom app expects `paycom_file` object (with .name attribute for CSV check).
            # If I pass a string path, it has no .name attribute.
            # I must pass a file object or mocking object.
            
            with open(paycom_path, 'rb') as f:
                # Mock streamlit upload (it has .name and .getvalue())
                # But run_comparison takes the object directly.
                # Logic: if paycom_file.name.lower().endswith('.csv')...
                # So I need an object with .name.
                
                class MockFile:
                    def __init__(self, path):
                        self.path = path
                        self.name = os.path.basename(path)
                    def read(self):
                        with open(self.path, 'rb') as f:
                            return f.read()
                    def seek(self, pos):
                        pass # Dummy
                    def __iter__(self):
                        with open(self.path, 'rb') as f:
                            for line in f:
                                yield line

                # But pandas read_csv accepts file-like or path.
                # If I pass MockFile to pd.read_csv, it might fail if it's not a real file handle.
                # But wait, run_comparison does:
                # paysom = pd.read_csv(paycom_file, ...)
                
                # So best to pass an open file handle.
                # File handle has .name!
                
                pass # Already valid.
                
            with open(paycom_path, 'rb') as pc_file:
                 res = run_paycom(uzio_path, pc_file)
                 print("Paycom Audit Success! Output bytes length:", len(res))
                 
            with open("verification_output/Paycom_Audit_Test.xlsx", "wb") as f:
                f.write(res)

        except Exception as e:
            print(f"Paycom Audit Failed: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("Paycom Sample not found.")

if __name__ == "__main__":
    test_audit_tools()
