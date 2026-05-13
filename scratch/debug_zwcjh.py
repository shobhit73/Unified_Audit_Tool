import sys
sys.path.append('c:/Users/shobhit.sharma/Downloads/Deduction Tool')
import pandas as pd
from apps.adp.total_comparison import find_header_and_data, calculate_totals, normalize_id, format_pay_date

# ADP Q1
with open('c:/Users/shobhit.sharma/Downloads/Deduction Tool/Prior Payroll Tool Dataset/Q1.csv', 'rb') as f:
    df_q1, top_q1, _ = find_header_and_data(f)

# ADP Q2
with open('c:/Users/shobhit.sharma/Downloads/Deduction Tool/Prior Payroll Tool Dataset/Q2-April.csv', 'rb') as f:
    df_q2, top_q2, _ = find_header_and_data(f)

# UZIO
with open('c:/Users/shobhit.sharma/Downloads/Deduction Tool/Prior Payroll Tool Dataset/Prior Payroll Register Report_2026-04-24-07-19-58.xlsx', 'rb') as f:
    df_uzio, uzio_top, sheet = find_header_and_data(f)

print('=== ADP Q1 - ZWCJH4WAH row ===')
adp_id_col = next((c for c in df_q1.columns if any(x in c.lower() for x in ['associate id', 'employee id', 'file #'])), None)
adp_date_col = next((c for c in df_q1.columns if any(x in c.lower() for x in ['pay date', 'period end', 'check date'])), None)
rows_q1 = df_q1[df_q1[adp_id_col] == 'ZWCJH4WAH']
print('ID col:', adp_id_col, '| Date col:', adp_date_col)
print(rows_q1[[adp_id_col, adp_date_col, 'GROSS PAY', 'REGULAR EARNINGS']].to_string())

print('\n=== UZIO - ZWCJH4WAH rows ===')
uzio_id_col = next((c for c in df_uzio.columns if any(x in c.lower() for x in ['associate id', 'employee id', 'file #'])), None)
uzio_date_col = next((c for c in df_uzio.columns if any(x in c.lower() for x in ['pay date', 'period end', 'check date'])), None)
rows_uzio = df_uzio[df_uzio[uzio_id_col] == 'ZWCJH4WAH']
print('ID col:', uzio_id_col, '| Date col:', uzio_date_col)
# Find Regular Wage col
reg_wage_cols = [c for c in df_uzio.columns if 'regular wage' in c.lower() or 'regular' in c.lower()]
print('Regular wage cols in Uzio:', reg_wage_cols)
if reg_wage_cols:
    print(rows_uzio[[uzio_id_col, uzio_date_col] + reg_wage_cols[:3]].to_string())

print('\n=== calculate_totals for REGULAR EARNINGS on Q1 ===')
tot, cols, emp_m, emp_c = calculate_totals(df_q1, top_q1, ['REGULAR EARNINGS'])
print('Columns found:', cols)
print('Employee totals for ZWCJH4WAH:')
for (eid, pd_), v in emp_m.items():
    if 'ZWCJH' in eid:
        print('  ', eid, pd_, v, '| rows:', emp_c[(eid, pd_)])

print('\n=== calculate_totals for Regular Wage on Uzio ===')
tot_u, cols_u, emp_m_u, emp_c_u = calculate_totals(df_uzio, uzio_top, ['Regular Wage'])
print('Columns found:', cols_u)
print('Employee totals for ZWCJH4WAH:')
for (eid, pd_), v in emp_m_u.items():
    if 'ZWCJH' in eid:
        print('  ', eid, pd_, v)
