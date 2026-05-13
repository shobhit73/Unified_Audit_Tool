"""Run from audit_fast_api/ as cwd to use its own utils/."""
import os, sys, tempfile
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "audit_fast_api"))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "audit_fast_api"))

from core.job_title_mapper import (
    load_amazon_catalog, extract_distinct_titles, write_mapping_csv,
)

cat = load_amazon_catalog()
print(f"Catalog: {len(cat)} entries (expect 28)")
assert len(cat) == 28
assert any(r["Job Title"] == "Non-DSP Related" for r in cat)
print("  OK")

# Build a tiny ADP-shape CSV so find_header_and_data works
import io
adp_csv = io.BytesIO((
    "Associate ID,Job Title Description,Department Description\n"
    "1,Sr. Ops Mgr,Ops\n"
    "2,,Warehouse\n"
    "3,Driver,Delivery\n"
    "4,,\n"
).encode())
out = extract_distinct_titles(adp_csv.getvalue(), "test.csv", "adp")
print(f"\nADP distinct titles: {out}")
assert "Sr. Ops Mgr" in out
assert "Warehouse" in out
assert "Driver" in out
print("  ADP fallback: OK")

paycom_csv = (
    "Employee_Code,Position,Business_Title,Job_Title_Description,Department_Desc\n"
    "1,Operations Manager,,,Ops\n"
    "2,,Lead Driver,,Delivery\n"
    "3,,,Walker,Foot\n"
    "4,,,,Dispatch\n"
).encode()
out = extract_distinct_titles(paycom_csv, "test.csv", "paycom")
print(f"\nPaycom distinct titles: {out}")
assert "Operations Manager" in out
assert "Lead Driver" in out
assert "Walker" in out
assert "Dispatch" in out
print("  Paycom 4-tier fallback: OK")

with tempfile.TemporaryDirectory() as tmp:
    p, n = write_mapping_csv(
        {"Sr. Ops Mgr": "Operations Manager", "Driver": "Driver"},
        "adp", tmp,
    )
    df = pd.read_csv(p)
    print(f"\nWritten CSV ({n} rows):\n{df}")
    assert n == 2
    assert list(df.columns) == ["DSP Job Title", "Amazon Job Title"]
print("  write_mapping_csv: OK")

print("\nAll MCP-side smoke tests passed.")
