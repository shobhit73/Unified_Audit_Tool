import sys, io, os
sys.path.insert(0, r"c:\Users\shobhit.sharma\Downloads\Deduction Tool")
from apps.adp.prior_payroll_sanity import detect_file_shape, read_input_file, drop_summary_rows, detect_grand_total_row


class Buf(io.BytesIO):
    def __init__(self, c, name):
        super().__init__(c); self.name = name


for label, p in [
    ("Carvan RAW (full quarter, per-pay-period)",
     r"C:\Users\shobhit.sharma\Downloads\Carvan Prior Payroll Setup\Prior Payroll Register Report_2026-05-02-10-15-34.xlsx"),
    ("Carvan Consolidated (already aggregated)",
     r"C:\Users\shobhit.sharma\Downloads\Carvan Prior Payroll Setup\Payroll_History_Q1_Consolidated.csv"),
    ("Travel Mgmt Q1",
     r"C:\Users\shobhit.sharma\Downloads\Travel Management Prior Payroll Setup\Q1.csv"),
]:
    with open(p, "rb") as f:
        c = f.read()
    buf = Buf(c, os.path.basename(p))
    df, _, _ = read_input_file(buf)
    df, _ = drop_summary_rows(df)
    df, _ = detect_grand_total_row(df)
    facts = detect_file_shape(df)
    print(f"\n--- {label} ---")
    print(f"  shape: {facts['detected_shape']}")
    print(f"  recommended: {facts['recommended_strategy']}")
    print(f"  reason: {facts['recommendation_reason']}")
    print(f"  associates: {facts['associates']}, span: {facts['date_span_days']}d, "
          f"max rows/eid: {facts['rows_per_associate_max']}, distinct pds: {facts['distinct_pay_dates']}")
