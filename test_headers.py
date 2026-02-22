import pandas as pd
import openpyxl

wb = openpyxl.load_workbook('templates/Uzio_Census_Template.xlsm')
ws = wb['Employee Details']

print("ROW 4 TEMPLATE HEADERS:")
for c in range(1, 20):
    val = ws.cell(row=4, column=c).value
    print(f"Col {c}: '{str(val)}'")
    
print("\nUZIO RAW MAPPING:")
from utils.audit_utils import UZIO_RAW_MAPPING
for k in list(UZIO_RAW_MAPPING.keys())[:15]:
    print(f"'{k}'")
