import pandas as pd

file_path = r"c:\Users\rohit.kaushik\Downloads\Unified Audit Tool\Prior payroll audit report (3).xlsx"
df = pd.read_excel(file_path, sheet_name="Employee Mismatches")

print("Value counts for Associate ID:")
print(df["Associate ID"].value_counts().head(20))

print("\nRows with Associate ID '012-88-3459':")
print(df[df["Associate ID"] == "012-88-3459"].to_string(index=False))

# Check for potential ID format issues
# Let's see if there are IDs that are just digits and others with hyphens
df['ID_digits'] = df['Associate ID'].astype(str).str.replace('-', '').str.lstrip('0')
id_counts = df['ID_digits'].value_counts()
print("\nPotential duplicate IDs (after normalization):")
print(id_counts[id_counts > 1].head(10))

if not id_counts[id_counts > 1].empty:
    first_dupe = id_counts.index[0]
    print(f"\nExample of potential format mismatch for normalized ID {first_dupe}:")
    print(df[df['ID_digits'] == first_dupe][["Associate ID", "Pay Date", "UZIO Item", "ADP Amount", "UZIO Amount"]])
