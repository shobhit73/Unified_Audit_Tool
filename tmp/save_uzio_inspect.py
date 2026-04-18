import pandas as pd
spec = r'c:\Users\shobhit.sharma\Downloads\Deduction Tool\templates\Uzio_Census_Template.xlsm'
df = pd.read_excel(spec, sheet_name='Employee Details', header=None, nrows=10)
with open('uzio_inspect.txt', 'w') as f:
    f.write(df.to_string())
