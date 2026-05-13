import pandas as pd

CENSUS = r"C:\Users\shobhit.sharma\Downloads\Census Report (1).xlsx"

TARGETS = {
    "320G3QMYW": "Jose Aizprua Almeida",
    "L76SO0DCC": "John Carter",
    "UAAHQ8SZU": "Bryson Emery",
    "YYKF28O4X": "Ekomobong Okon",
    "43IY17GC7": "Taylor Petterborg",
    "VADWRTFZ8": "Bryce Popolis",
    "VS0Y2GIEK": "Jeferson Rodas Ambrosio",
    "2X6HNC4MF": "Tevita Taukeiaho",
    "DVHU5OQC4": "Zachary Tucker",
}

df = pd.read_excel(CENSUS, sheet_name="Data", header=0, dtype=str)
df.columns = [str(c).strip() for c in df.columns]
print(f"Loaded {len(df)} rows.\n")

aid_col = "Associate ID"
df[aid_col] = df[aid_col].astype(str).str.strip()

# Show fields of interest
keep = ["Associate ID", "Legal First Name", "Legal Last Name",
        "Position Status", "Job Title Description", "Regular Pay Rate Amount",
        "Hire Date", "Termination Date"]

found = []
not_found = []
for tid, tname in TARGETS.items():
    hit = df[df[aid_col] == tid]
    if hit.empty:
        not_found.append((tid, tname))
    else:
        r = hit.iloc[0]
        found.append({
            "Associate ID": tid,
            "Expected Name": tname,
            "Actual Name": f"{r['Legal First Name']} {r['Legal Last Name']}",
            "Status": r.get("Position Status", ""),
            "Job Title": r.get("Job Title Description", ""),
            "Rate": r.get("Regular Pay Rate Amount", ""),
            "Hire Date": str(r.get("Hire Date", ""))[:10],
            "Term Date": str(r.get("Termination Date", ""))[:10] if pd.notna(r.get("Termination Date")) else "",
        })

print(f"=== Found ({len(found)}/{len(TARGETS)}) ===")
if found:
    print(pd.DataFrame(found).to_string(index=False))

print(f"\n=== NOT Found ({len(not_found)}) ===")
for tid, tname in not_found:
    print(f"  {tid}  {tname}")

# For not-found IDs, also try a name-based search to see if they exist with different IDs
if not_found:
    print(f"\n=== Name-based search for not-found IDs ===")
    for tid, tname in not_found:
        first = tname.split()[0].upper() if tname else ""
        last = tname.split()[-1].upper() if tname else ""
        if not first or not last:
            continue
        hit = df[df["Legal First Name"].astype(str).str.upper().str.contains(first, na=False)
               & df["Legal Last Name"].astype(str).str.upper().str.contains(last, na=False)]
        if not hit.empty:
            print(f"  {tid} ({tname}) — found by name with different ID(s):")
            print(hit[["Associate ID", "Legal First Name", "Legal Last Name", "Position Status", "Hire Date"]].to_string(index=False))
        else:
            print(f"  {tid} ({tname}) — NOT in census by ID OR by name")
