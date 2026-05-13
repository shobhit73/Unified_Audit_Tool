import sys
sys.path.append('c:/Users/shobhit.sharma/Downloads/Deduction Tool')
import pandas as pd
from utils.audit_utils import clean_money_val

# Read Q1 raw - no filter
df_raw = pd.read_csv('c:/Users/shobhit.sharma/Downloads/Deduction Tool/Prior Payroll Tool Dataset/Q1.csv')
print('Raw Q1 rows:', len(df_raw))

last = df_raw.iloc[-1]
prev = df_raw.iloc[-2]
print('\nLast row ASSOCIATE ID:', last['ASSOCIATE ID'], '| GROSS PAY:', last['GROSS PAY'])
print('Prev row ASSOCIATE ID:', prev['ASSOCIATE ID'], '| GROSS PAY:', prev['GROSS PAY'])

# Check shared_cols logic
shared_cols = 0
for c in df_raw.columns[:5]:
    v_last = str(last[c]).strip()
    v_prev = str(prev[c]).strip()
    is_same = (v_last == v_prev and v_last.lower() != 'nan')
    print('col=' + c + '  last=' + repr(v_last) + '  prev=' + repr(v_prev) + '  same=' + str(is_same))
    if is_same:
        shared_cols += 1
print('shared_cols:', shared_cols)

# Now check the actual values
print()
print('GROSS PAY last raw value:', repr(last['GROSS PAY']))
try:
    val_last = clean_money_val(last['GROSS PAY'])
    print('clean_money_val(last GROSS PAY):', val_last)
    sum_rest = sum(clean_money_val(x) for x in df_raw['GROSS PAY'].iloc[:-1])
    print('sum_rest GROSS PAY:', sum_rest)
    ratio = val_last / sum_rest if sum_rest > 0 else 'N/A'
    print('ratio:', ratio)
    print('Threshold check (ratio within 5%):', abs(val_last - sum_rest) < sum_rest * 0.05)
except Exception as e:
    print('Error:', e)

# Also look at the actual find_header_and_data result
print('\n--- Testing find_header_and_data output ---')
from apps.adp.total_comparison import find_header_and_data

with open('c:/Users/shobhit.sharma/Downloads/Deduction Tool/Prior Payroll Tool Dataset/Q1.csv', 'rb') as f:
    df, top, _ = find_header_and_data(f)

print('find_header_and_data returned rows:', len(df))
rows_z = df[df['ASSOCIATE ID'] == 'ZWCJH4WAH']
print('ZWCJH4WAH rows after filter:')
print(rows_z[['ASSOCIATE ID', 'PAY DATE', 'GROSS PAY', 'REGULAR EARNINGS']].to_string())
