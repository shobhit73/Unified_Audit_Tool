import pandas as pd
import warnings
warnings.filterwarnings('ignore')

path = r'c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\License Sample\Emergency and Licence Report.xlsx'
df = pd.read_excel(path, sheet_name='Data', dtype=str)
for c in df.columns:
    print(repr(c))
print("---")
print(f"Rows: {len(df)}")
