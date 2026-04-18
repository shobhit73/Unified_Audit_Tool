import pandas as pd
df = pd.read_excel(r'c:\Users\shobhit.sharma\Downloads\Deduction Tool\templates\Uzio_Census_Template.xlsm', sheet_name='Employee Details', header=3, nrows=1)
print(list(df.columns))
