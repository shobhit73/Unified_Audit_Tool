import pandas as pd

file_path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Prior Payroll Tool Dataset\Carvan\Copy of Payroll History Q2.csv"
df = pd.read_csv(file_path)

# Ensure PAY DATE is string or datetime
df['PAY DATE'] = df['PAY DATE'].astype(str)

date_to_check = '05/01/2026'
df_date = df[df['PAY DATE'] == date_to_check]

print(f"--- Analysis for {date_to_check} ---")
print(f"Total rows: {len(df_date)}")
print(f"Unique Names: {df_date['NAME'].nunique()}")
print(f"Unique Associate IDs: {df_date['ASSOCIATE ID'].nunique()}")

# Check for duplicates (multiple rows for same ID)
counts = df_date['ASSOCIATE ID'].value_counts()
duplicates = counts[counts > 1]
if not duplicates.empty:
    print(f"\nEmployees with multiple entries on {date_to_check}:")
    for aid, count in duplicates.items():
        name = df_date[df_date['ASSOCIATE ID'] == aid]['NAME'].iloc[0]
        print(f"  - {name} ({aid}): {count} rows")
else:
    print("\nNo employees with multiple entries on this date.")
