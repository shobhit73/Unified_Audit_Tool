import pandas as pd
import warnings
warnings.filterwarnings('ignore')

path = r'c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\License Sample\Emergency and Licence Report.xlsx'

df = pd.read_excel(path, sheet_name='Data', dtype=str)
print("Columns:")
for i, c in enumerate(df.columns.tolist()):
    print(f"  [{i}] {repr(c)}")
print(f"\nTotal rows: {len(df)}")
print("\nSample row 0:")
print(df.iloc[0].to_dict())
