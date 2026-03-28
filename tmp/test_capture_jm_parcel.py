import pandas as pd
import re
import numpy as np
from collections import defaultdict
import sys
sys.stdout.reconfigure(encoding='utf-8')

def norm_colname(cIdx: str) -> str:
    if cIdx is None: return ""
    c = str(cIdx).replace("\n", " ").replace("\r", " ")
    c = c.replace("\u00A0", " ")
    c = re.sub(r'\(.*?\)', '', c)
    c = re.sub(r"\s+", " ", c).strip()
    c = c.replace("*", "")
    return c

def find_col(df_cols, *candidate_names):
    norm_map = {norm_colname(c).casefold(): c for c in df_cols}
    for cand in candidate_names:
        clean_cand = norm_colname(cand).casefold()
        if clean_cand in norm_map:
            return norm_map[clean_cand]
    return ""

UZIO_RAW_MAPPING = {
    'Employee ID*': 'Employee ID',
    'Employee First Name*': 'First Name',
    'Employee Last Name*': 'Last Name',
    'Employment Status*': 'Employment Status',
    'Date of Hire*': 'Hire Date',
    'Official Email*': 'Work Email',
    'Job Title': 'Job Title',
}

ADP_FIELD_MAP = {
    'Employee ID': ['Associate ID', 'AssociateID', 'Employee ID'],
    'First Name': ['Legal First Name', 'First Name'],
    'Last Name': ['Legal Last Name', 'Last Name'],
    'Employment Status': ['Position Status', 'Employment Status'],
    'Hire Date': ['Hire/Rehire Date', 'Hire Date'],
    'Work Email': ['Work Contact: Work Email', 'Work Email'],
    'Job Title': ['Job Title Description', 'Job Title'],
}

uz_path = r"C:\Users\shobhit.sharma\Downloads\JM Parcel\Multi_Client_JM Parcel Service LLC_Employee_Census.xlsm"
adp_path = r"C:\Users\shobhit.sharma\Downloads\JM Parcel\ADP JM Parcel Employee Census 26th March.xlsx"

# 1. Read Uzio
df_uzio = pd.read_excel(uz_path, sheet_name='Employee Details', header=3)
df_uzio.columns = [str(c).strip() for c in df_uzio.columns]
norm_mapping = {norm_colname(k).casefold(): v for k, v in UZIO_RAW_MAPPING.items()}
new_cols = []
for col in df_uzio.columns:
    nc = norm_colname(col).casefold()
    if nc in norm_mapping:
        new_cols.append(norm_mapping[nc])
    else:
        new_cols.append(col)
df_uzio.columns = new_cols

# 2. Read ADP
df_adp = pd.read_excel(adp_path)
df_adp.columns = [norm_colname(c) for c in df_adp.columns]

# 3. Resolve
uz_to_adp = {}
for internal_name, candidates in ADP_FIELD_MAP.items():
    found = find_col(df_adp.columns, *candidates)
    uz_to_adp[internal_name] = found

print("-" * 80)
print(f"{'Field (Standard)':<25} | {'Source ADP Column Found'}")
print("-" * 80)
for k, v in uz_to_adp.items():
    print(f"{k:<25} | {v if v else '❌ NOT FOUND'}")
print("-" * 80)

# Check first 3 employees across all mapped fields
print("\nDISCREPANCY CHECK (SAMPLE):")
sample_ids = df_adp['Associate ID'].head(3).tolist()
for eid in sample_ids:
    row_match = df_uzio[df_uzio['Employee ID'].astype(str) == str(eid)]
    if not row_match.empty:
        print(f"\nEmployee: {eid}")
        for field in ADP_FIELD_MAP.keys():
            if field == 'Employee ID': continue
            adp_col = uz_to_adp.get(field)
            if adp_col:
                adp_val = df_adp[df_adp['Associate ID'] == eid][adp_col].iloc[0]
                uz_val = row_match[field].iloc[0]
                print(f"  {field:<18}: Uzio='{uz_val}' vs ADP='{adp_val}'")
