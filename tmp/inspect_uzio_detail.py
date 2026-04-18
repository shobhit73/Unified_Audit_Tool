import pandas as pd
spec = r'c:\Users\shobhit.sharma\Downloads\Deduction Tool\templates\Uzio_Census_Template.xlsm'
df = pd.read_excel(spec, sheet_name='Employee Details', header=None, nrows=10)
print(df)
