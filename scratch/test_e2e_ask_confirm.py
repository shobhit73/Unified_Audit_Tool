"""End-to-end simulation: ask -> recommend -> user confirms -> apply.

Tests both modules (audit_fast_api core + Streamlit module) on three real
client files. Verifies:
  1. ask-mode returns no file but rich detection JSON
  2. recommended_strategy aligns with the file's actual shape
  3. follow-up call with the recommendation produces a valid CSV
  4. follow-up call with the OPPOSITE strategy still works (override)
  5. legacy callers passing 'full_quarter' / 'preserve_pay_periods'
     directly still work without breaking
"""
import sys, io, os
sys.path.insert(0, r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\audit_fast_api")
sys.path.insert(0, r"c:\Users\shobhit.sharma\Downloads\Deduction Tool")

from core.adp.prior_payroll_sanity import run_adp_prior_payroll_sanity as run_mcp
import importlib
import apps.adp.prior_payroll_sanity as streamlit_module
importlib.reload(streamlit_module)


class Buf(io.BytesIO):
    def __init__(self, c, name):
        super().__init__(c); self.name = name


CASES = [
    ("Carvan RAW (per-pay-period, full quarter)",
     r"C:\Users\shobhit.sharma\Downloads\Carvan Prior Payroll Setup\Prior Payroll Register Report_2026-05-02-10-15-34.xlsx",
     "full_quarter"),
    ("Carvan Consolidated (already aggregated)",
     r"C:\Users\shobhit.sharma\Downloads\Carvan Prior Payroll Setup\Payroll_History_Q1_Consolidated.csv",
     None),
    ("Travel Mgmt Q1 (already aggregated)",
     r"C:\Users\shobhit.sharma\Downloads\Travel Management Prior Payroll Setup\Q1.csv",
     None),
]

print("=" * 70)
print("MCP module (core/adp/prior_payroll_sanity.py)")
print("=" * 70)

for label, path, expected_rec in CASES:
    print(f"\n[{label}]")
    with open(path, "rb") as f:
        content = f.read()
    fname = os.path.basename(path)

    # 1. Default call (no aggregation_strategy) -> ask mode
    csv_b, summary = run_mcp(content, fname)
    assert summary["mode"] == "detection_only", f"Expected ask mode, got {summary['mode']}"
    assert csv_b == b"", f"Expected empty bytes in ask mode, got {len(csv_b)}"
    rec = summary["recommended_strategy"]
    assert rec == expected_rec, f"Expected rec={expected_rec}, got {rec}"
    print(f"  [OK] default = ask mode, no file written, rec={rec}")
    print(f"       facts: associates={summary['facts']['associates']}, "
          f"span={summary['facts']['date_span_days']}d, "
          f"max_rows/eid={summary['facts']['rows_per_associate_max']}")

    # 2. Explicit 'ask' -> same as default
    csv_b2, summary2 = run_mcp(content, fname, aggregation_strategy="ask")
    assert summary2["mode"] == "detection_only"
    print(f"  [OK] explicit 'ask' behaves identically")

    # 3. Explicit full_quarter
    csv_b3, summary3 = run_mcp(content, fname, aggregation_strategy="full_quarter")
    assert csv_b3 != b"", "full_quarter should produce a file"
    assert summary3.get("mode") in ("aggregate", "none"), f"unexpected mode: {summary3.get('mode')}"
    print(f"  [OK] full_quarter produced {summary3['output_rows']} rows")

    # 4. Explicit preserve_pay_periods
    csv_b4, summary4 = run_mcp(content, fname, aggregation_strategy="preserve_pay_periods")
    assert csv_b4 != b"", "preserve_pay_periods should produce a file"
    print(f"  [OK] preserve_pay_periods produced {summary4['output_rows']} rows")

print("\n\n" + "=" * 70)
print("Streamlit module (apps/adp/prior_payroll_sanity.py) -- detect_file_shape only")
print("=" * 70)

for label, path, expected_rec in CASES:
    print(f"\n[{label}]")
    with open(path, "rb") as f:
        content = f.read()
    buf = Buf(content, os.path.basename(path))
    df, _, _ = streamlit_module.read_input_file(buf)
    df, _ = streamlit_module.drop_summary_rows(df)
    df, _ = streamlit_module.detect_grand_total_row(df)
    facts = streamlit_module.detect_file_shape(df)
    rec = facts["recommended_strategy"]
    assert rec == expected_rec, f"Streamlit rec mismatch: expected {expected_rec}, got {rec}"
    print(f"  [OK] detect_file_shape rec={rec}, shape={facts['detected_shape']}")
    print(f"       reason: {facts['recommendation_reason'][:100]}")

print("\n\nAll assertions passed.")
