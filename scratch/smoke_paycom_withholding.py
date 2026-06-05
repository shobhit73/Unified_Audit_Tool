"""Headless smoke test for the Paycom withholding audit after the
inline-data refactor. Mimics what render_ui does but skips Streamlit."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from apps.paycom.withholding_audit import (
    _load_mapping_df, _load_labels_by_state, _load_filing_status_code,
    _autodetect_paycom_cols, run_withholding_audit, build_report_bytes,
)

PAYCOM_PATH = r"C:\Users\rohit.kaushik\Downloads\Chief Delivery\20260528004100_Advanced_Report_Writer_b4de73d1.csv"
UZIO_PATH   = r"C:\Users\rohit.kaushik\Downloads\Chief Delivery\Chief Delivery.csv"
OUT_PATH    = r"C:\Users\rohit.kaushik\Downloads\Chief Delivery\REBUILD_Chief_Delivery_Paycom_Withholding_Audit.xlsx"


def section(t): print("\n" + "=" * 72); print(t); print("=" * 72)


def main():
    section("Step 1 — load inlined config")
    mapping_df = _load_mapping_df()
    labels = _load_labels_by_state()
    filing = _load_filing_status_code()
    print(f"  Mapping rows:           {len(mapping_df)}")
    print(f"  Filing-status codes:    {len(filing)}")
    print(f"  Jurisdictions w/labels: {len(labels)}")

    section("Step 2 — read Chief Delivery files")
    paycom_df = pd.read_csv(PAYCOM_PATH, dtype=str, keep_default_na=False)
    uzio_df   = pd.read_csv(UZIO_PATH, dtype=str, keep_default_na=False)
    print(f"  Paycom: {paycom_df.shape}")
    print(f"  UZIO:   {uzio_df.shape}")
    emp_id_col, status_col, state_col, fn_col, ln_col = _autodetect_paycom_cols(paycom_df)
    print(f"  Auto-detected Paycom cols: id={emp_id_col!r}, status={status_col!r}, "
          f"state={state_col!r}, fn={fn_col!r}, ln={ln_col!r}")

    section("Step 3 — run audit")
    s_df, act_df, all_df, miss_df, f_map_df, ui_map_df, rules_df = run_withholding_audit(
        paycom_df=paycom_df, uzio_long_df=uzio_df, mapping_df=mapping_df,
        labels_by_state=labels, filing_map=filing,
        paycom_emp_id_col=emp_id_col, paycom_status_col=status_col,
        paycom_state_col=state_col, paycom_fn_col=fn_col, paycom_ln_col=ln_col,
    )
    print("Summary:")
    for _, r in s_df.iterrows():
        print(f"  {r['Metric']:<45s} {r['Value']}")

    section("Step 4 — write report")
    data = build_report_bytes(s_df, act_df, all_df, miss_df, f_map_df, ui_map_df, rules_df)
    with open(OUT_PATH, "wb") as f:
        f.write(data)
    print(f"  Wrote {OUT_PATH}  ({len(data):,} bytes)")


if __name__ == "__main__":
    main()
