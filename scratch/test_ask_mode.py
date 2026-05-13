"""Verify ask-mode detection on full-quarter and partial-quarter ADP files."""
import sys
sys.path.insert(0, r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\audit_fast_api")

from core.adp.prior_payroll_sanity import run_adp_prior_payroll_sanity, detect_file_shape, read_input_bytes, drop_summary_rows, detect_grand_total_row

def test_ask(label, path):
    with open(path, "rb") as f:
        c = f.read()
    csv_b, summary = run_adp_prior_payroll_sanity(c, path.split("\\")[-1], aggregation_strategy="ask")
    print(f"\n=== {label} (ask mode) ===")
    print(f"  csv_bytes len: {len(csv_b)} (expect 0 in ask mode)")
    print(f"  mode: {summary['mode']}")
    print(f"  recommended: {summary['recommended_strategy']}")
    print(f"  reason: {summary['recommendation_reason']}")
    print(f"  facts:")
    for k, v in summary['facts'].items():
        print(f"    {k}: {v}")

# Full-quarter Carvan file (per-pay-period across 90 days)
test_ask("Carvan Q1 RAW",
    r"C:\Users\shobhit.sharma\Downloads\Carvan Prior Payroll Setup\Prior Payroll Register Report_2026-05-02-10-15-34.xlsx")

# Already-aggregated file
test_ask("Carvan Q1 Consolidated (already aggregated)",
    r"C:\Users\shobhit.sharma\Downloads\Carvan Prior Payroll Setup\Payroll_History_Q1_Consolidated.csv")

# Travel Mgmt Q1 (already 1 row per associate, 90 day span)
test_ask("Travel Mgmt Q1",
    r"C:\Users\shobhit.sharma\Downloads\Travel Management Prior Payroll Setup\Q1.csv")

# Verify default is ask
print("\n=== Default-default test ===")
with open(r"C:\Users\shobhit.sharma\Downloads\Travel Management Prior Payroll Setup\Q1.csv", "rb") as f:
    c = f.read()
csv_b, summary = run_adp_prior_payroll_sanity(c, "Q1.csv")  # no aggregation_strategy at all
print(f"  mode (should be 'detection_only'): {summary['mode']}")

# Verify explicit full_quarter still works
print("\n=== Explicit full_quarter test ===")
csv_b, summary = run_adp_prior_payroll_sanity(c, "Q1.csv", aggregation_strategy="full_quarter")
print(f"  mode: {summary['mode']}, output_rows: {summary['output_rows']}")

# Verify explicit preserve_pay_periods still works
print("\n=== Explicit preserve_pay_periods test ===")
csv_b, summary = run_adp_prior_payroll_sanity(c, "Q1.csv", aggregation_strategy="preserve_pay_periods")
print(f"  mode: {summary['mode']}, output_rows: {summary['output_rows']}")
