import sys
sys.path.append('c:/Users/shobhit.sharma/Downloads/Deduction Tool')
import pandas as pd

# Simulate what auto_detect_files does — test each file
files_to_test = {
    'Q1.csv': 'c:/Users/shobhit.sharma/Downloads/Deduction Tool/Prior Payroll Tool Dataset/Q1.csv',
    'Q2-April.csv': 'c:/Users/shobhit.sharma/Downloads/Deduction Tool/Prior Payroll Tool Dataset/Q2-April.csv',
    'Prior Payroll Register.xlsx': 'c:/Users/shobhit.sharma/Downloads/Deduction Tool/Prior Payroll Tool Dataset/Prior Payroll Register Report_2026-04-24-07-19-58.xlsx',
    'Earning Mapping.csv': 'c:/Users/shobhit.sharma/Downloads/Deduction Tool/Prior Payroll Tool Dataset/Travel Management Earning Mapping.csv',
    'Deduction Mapping.csv': 'c:/Users/shobhit.sharma/Downloads/Deduction Tool/Prior Payroll Tool Dataset/Travel Management Deduction Mapping final 2.csv',
    'Contribution Mapping.csv': 'c:/Users/shobhit.sharma/Downloads/Deduction Tool/Prior Payroll Tool Dataset/Travel Management Contribution Mapping.csv',
    'Voluntary Deduction.csv': 'c:/Users/shobhit.sharma/Downloads/Deduction Tool/Prior Payroll Tool Dataset/Travel Management Voluntary Deduction.csv',
    'Tax Mapping.csv': 'c:/Users/shobhit.sharma/Downloads/Deduction Tool/Prior Payroll Tool Dataset/travel_managment_tax_mapping_q1.csv',
}

for label, path in files_to_test.items():
    try:
        name = path.lower()
        if name.endswith('.csv'):
            df_peek = pd.read_csv(path, nrows=3, dtype=str)
            cols = [str(c).lower().strip() for c in df_peek.columns]
        else:
            xls = pd.ExcelFile(path)
            cols = []
            for sheet in xls.sheet_names:
                if 'criteria' in sheet.lower():
                    continue
                df_peek = pd.read_excel(xls, sheet_name=sheet, header=None, nrows=5, dtype=str)
                for i, row in df_peek.iterrows():
                    row_vals = [str(v).lower().strip() for v in row if pd.notna(v) and str(v).strip()]
                    if any(x in ' '.join(row_vals) for x in ['employee id', 'associate id', 'source earning', 'source deduction', 'source tax']):
                        cols = row_vals
                        break
                if cols:
                    break
            if not cols:
                for sheet in xls.sheet_names:
                    if 'criteria' not in sheet.lower():
                        df_peek = pd.read_excel(xls, sheet_name=sheet, nrows=3, dtype=str)
                        cols = [str(c).lower().strip() for c in df_peek.columns]
                        break

        col_str = " | ".join(cols)

        if 'source tax code name' in col_str:
            role = 'Taxes Mapping'
        elif 'source earning code name' in col_str:
            role = 'Earnings Mapping'
        elif 'source deduction code name' in col_str:
            role = 'Deductions Mapping'
        elif 'source contribution code name' in col_str:
            role = 'Contributions Mapping'
        elif 'employee id' in col_str and any(x in col_str for x in ['regular wage', 'gross pay', 'overtime', 'pay date', 'first name']) and 'associate id' not in col_str:
            role = 'UZIO Register'
        elif 'associate id' in col_str and any(x in col_str for x in ['regular earnings', 'gross pay', 'regular hours', 'total earnings', 'net pay']):
            role = 'ADP Payroll'
        else:
            role = 'Unknown'

        print(f'{label:35s} -> {role}')
        if role == 'Unknown':
            print(f'  Sample cols: {cols[:8]}')
    except Exception as e:
        print(f'{label:35s} -> ERROR: {e}')
