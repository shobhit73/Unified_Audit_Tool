import pandas as pd
import re

UZIO = r'C:\Users\rohit.kaushik\Downloads\Chief Delivery\payroll\Prior Payroll Register Report_2026-06-01-05-38-22.xlsx'

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 250)

xls = pd.ExcelFile(UZIO)
print('Sheets:', xls.sheet_names)
for sn in xls.sheet_names:
    print(f'\n=== Sheet: {sn} ===')
    df_peek = pd.read_excel(xls, sheet_name=sn, header=None, nrows=10)
    print(df_peek.shape)
    for i, row in df_peek.iterrows():
        vals = [str(v) for v in row.tolist() if pd.notna(v)]
        print(f'Row {i} ({len(vals)} non-empty):', vals[:25])

print('\n=== Looking for "bonus" columns specifically ===')
# Use the same logic as find_header_and_data_uzio
target_sheet = xls.sheet_names[0]
if len(xls.sheet_names) > 1 and "criteria" in xls.sheet_names[0].lower():
    target_sheet = xls.sheet_names[1]
print('Target sheet:', target_sheet)

df_peek = pd.read_excel(xls, sheet_name=target_sheet, header=None, nrows=50)
header_idx = 0
for i, row in df_peek.iterrows():
    row_str = " ".join([str(x).lower() for x in row if pd.notna(x)])
    if "employee id" in row_str or "employee name" in row_str:
        header_idx = i
        break
print('Header row index:', header_idx)

df = pd.read_excel(xls, sheet_name=target_sheet, header=header_idx)
header_top = None
if header_idx > 0:
    header_top = df_peek.iloc[header_idx - 1].tolist()

print('\nheader_top values (non-null):')
if header_top:
    for i, v in enumerate(header_top):
        if pd.notna(v) and str(v).strip():
            print(f'  col {i}: {v!r}')

print('\nMain header values containing "bonus":')
for i, c in enumerate(df.columns):
    if 'bonus' in str(c).lower():
        top = header_top[i] if header_top and i < len(header_top) else None
        print(f'  col {i}: main={c!r}, top={top!r}')

print('\nAll columns near "Bonus" header in top row:')
if header_top:
    for i, v in enumerate(header_top):
        if pd.notna(v) and 'bonus' in str(v).lower():
            # Print the section
            end_i = len(df.columns)
            for j in range(i+1, len(header_top)):
                if pd.notna(header_top[j]) and str(header_top[j]).strip():
                    end_i = j
                    break
            print(f'  Section "{v}" spans columns {i}..{end_i-1}:')
            for k in range(i, end_i):
                col = df.columns[k]
                # Sample some values
                vals = df.iloc[:, k].dropna().head(5).tolist()
                tot = pd.to_numeric(df.iloc[:, k], errors='coerce').sum()
                print(f'    col {k}: header={col!r}  sum~{tot:.2f}  sample={vals[:3]}')
