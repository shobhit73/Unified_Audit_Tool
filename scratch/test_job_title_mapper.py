"""Smoke test: catalog load + title extraction + fallback chain."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from utils.job_title_mapper import (
    load_amazon_catalog, extract_dsp_titles, _find_column,
)

# 1. Catalog loads and filters empty rows
cat = load_amazon_catalog()
print(f"Catalog rows: {len(cat)} (expect 28, drops empty J029/J030)")
assert len(cat) == 28
assert set(cat.columns) == {"Job Code", "Job Category", "Job Title"}
assert "DSP Owner" in cat["Job Title"].values
assert "Driver" in cat["Job Title"].values
assert "Non-DSP Related" in cat["Job Title"].values
print("  Catalog: OK")

# 2. ADP extraction with both Job Title + Department fallback
adp_df = pd.DataFrame([
    {"Associate ID": "1", "Job Title Description": "Sr. Operations Mgr", "Department Description": "Ops"},
    {"Associate ID": "2", "Job Title Description": "",                   "Department Description": "Warehouse"},
    {"Associate ID": "3", "Job Title Description": "Driver",             "Department Description": "Delivery"},
    {"Associate ID": "4", "Job Title Description": None,                 "Department Description": ""},
])
out = extract_dsp_titles(adp_df, "adp")
print(f"\nADP distinct titles ({len(out)}): {out}")
assert "Sr. Operations Mgr" in out, "primary should be picked when present"
assert "Warehouse" in out, "Department fallback should fire when JT is blank"
assert "Driver" in out
assert "" not in out
print("  ADP fallback: OK")

# 3. Paycom extraction with all 4 tier fallbacks
paycom_df = pd.DataFrame([
    {"Position": "Operations Manager", "Business_Title": "",         "Job_Title_Description": "",       "Department_Desc": "Ops"},
    {"Position": "",                   "Business_Title": "Lead Driver","Job_Title_Description": "",       "Department_Desc": "Delivery"},
    {"Position": "",                   "Business_Title": "",         "Job_Title_Description": "Walker", "Department_Desc": "Foot"},
    {"Position": "",                   "Business_Title": "",         "Job_Title_Description": "",       "Department_Desc": "Dispatch"},
])
out = extract_dsp_titles(paycom_df, "paycom")
print(f"\nPaycom distinct titles ({len(out)}): {out}")
assert "Operations Manager" in out
assert "Lead Driver" in out
assert "Walker" in out
assert "Dispatch" in out
print("  Paycom 4-tier fallback: OK")

# 4. Resolved field map override
df_w_quirk_cols = pd.DataFrame([{"WeirdJobCol": "Helper", "WeirdDeptCol": "Backup"}])
out = extract_dsp_titles(
    df_w_quirk_cols, "adp",
    resolved_field_map={"Job Title": "WeirdJobCol", "Department": "WeirdDeptCol"},
)
print(f"\nResolved-field-map override: {out}")
assert "Helper" in out
print("  resolved_field_map override: OK")

# 5. MCP-side helpers
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "audit_fast_api"))
from core.job_title_mapper import (
    load_amazon_catalog as mcp_catalog,
    write_mapping_csv,
)
cat_dicts = mcp_catalog()
print(f"\nMCP catalog dicts: {len(cat_dicts)} entries")
assert len(cat_dicts) == 28

import tempfile
with tempfile.TemporaryDirectory() as tmp:
    p, n = write_mapping_csv(
        {"Sr. Ops Mgr": "Operations Manager", "Driver": "Driver", "": "skip-me"},
        "adp", tmp,
    )
    saved = pd.read_csv(p)
    print(f"\nWritten CSV ({n} rows):\n{saved}")
    assert n == 2, "blank dsp_title row should be skipped"
    assert list(saved.columns) == ["DSP Job Title", "Amazon Job Title"]
print("  MCP write_mapping_csv: OK")

print("\nAll smoke tests passed.")
