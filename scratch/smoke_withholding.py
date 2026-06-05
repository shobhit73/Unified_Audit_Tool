"""Smoke-test for the rebuilt withholding audit.
Runs the pure-data pipeline on the real sample files, writes the report
to disk, and prints a short comparison summary.
"""

from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from apps.adp.withholding_audit import (
    AuditOptions, run_audit, build_workbook,
    detect_source, read_uploaded,
    load_filing_status_map, FILING_STATUS_MAP_FALLBACK,
)


class FakeUploadedFile:
    """Mimics Streamlit's UploadedFile for read_uploaded()."""
    def __init__(self, path: str):
        self.name = os.path.basename(path)
        with open(path, "rb") as f:
            self._raw = f.read()

    def getvalue(self):
        return self._raw


SAMPLES_DIR = r"C:\Users\rohit.kaushik\Downloads\Unified Audit Tool"
UZIO_PATH = os.path.join(SAMPLES_DIR, "jm_uzio_federal.csv")
ADP_PATH = os.path.join(SAMPLES_DIR, "SIT FIT Withholding Report (2).xlsx")
BASELINE_PATH = os.path.join(SAMPLES_DIR, "ADP_vs_UZIO_FIT_SIT_Mismatch_Report_JMParcel_16_04_2026_1206.xlsx")
OUT_PATH = os.path.join(SAMPLES_DIR, "REBUILD_ADP_vs_UZIO_Withholding_JMParcel.xlsx")


def main():
    print("=" * 72)
    print("Step 0: confirm filing status_code.txt is being loaded")
    print("=" * 72)
    fs = load_filing_status_map()
    print(f"  Hardcoded fallback entries: {len(FILING_STATUS_MAP_FALLBACK)}")
    print(f"  Merged (file + fallback):   {len(fs)}")
    extra = sorted(set(fs) - set(FILING_STATUS_MAP_FALLBACK))
    print(f"  Codes in file not in hardcoded fallback: {len(extra)} -> {extra[:8]}{'...' if len(extra) > 8 else ''}")

    print()
    print("=" * 72)
    print("Step 1: read files and auto-detect source")
    print("=" * 72)
    uzio_file = FakeUploadedFile(UZIO_PATH)
    adp_file = FakeUploadedFile(ADP_PATH)
    df_u = read_uploaded(uzio_file)
    df_a = read_uploaded(adp_file)
    print(f"  {uzio_file.name!r}  detected as: {detect_source(df_u)}  (expected: uzio)")
    print(f"  {adp_file.name!r}  detected as: {detect_source(df_a)}   (expected: adp)")

    print()
    print("=" * 72)
    print("Step 2: run audit")
    print("=" * 72)
    options = AuditOptions()
    result = run_audit(df_a, df_u, options)

    print()
    print("Summary metrics:")
    for _, row in result.summary_metrics.iterrows():
        print(f"  {row['Metric']:<55s} {row['Value']}")

    print()
    print("Mismatch summary (Category x Field):")
    if result.mismatch_summary.empty:
        print("  (none)")
    else:
        for _, row in result.mismatch_summary.iterrows():
            print(f"  [{row['Category']:<22s}] {row['Field Key']:<42s} "
                  f"{row['Mismatch Count']:>4d}  ({row['Unique Employee Count']} employees)")

    print()
    print("Category totals across all mismatches:")
    if result.mismatches.empty:
        print("  (none)")
    else:
        for cat, n in result.mismatches['CATEGORY'].value_counts().items():
            print(f"  {cat:<24s} {n}")

    print()
    print("False positives filtered (top reasons):")
    if result.false_positives_filtered.empty:
        print("  (none)")
    else:
        fp = result.false_positives_filtered.groupby("REASON").size().sort_values(ascending=False)
        for reason, n in fp.head(5).items():
            short = reason if len(reason) < 80 else reason[:77] + "..."
            print(f"  {n:>4d}  {short}")

    print()
    print("=" * 72)
    print("Step 3: write workbook")
    print("=" * 72)
    data = build_workbook(result)
    with open(OUT_PATH, "wb") as f:
        f.write(data)
    print(f"  Wrote {OUT_PATH}  ({len(data):,} bytes)")

    print()
    print("=" * 72)
    print("Step 4: diff against baseline report")
    print("=" * 72)
    if not os.path.exists(BASELINE_PATH):
        print("  Baseline not found, skipping diff.")
        return
    baseline_summary = pd.read_excel(BASELINE_PATH, sheet_name="Mismatch Summary", dtype=str)
    print()
    print(f"{'FIELD_KEY':<40s} {'baseline':>10s} {'rebuild':>10s}  {'delta':>10s}")
    print("-" * 75)
    base_counts = {r["FIELD_KEY"]: int(r["mismatch_rows"]) for _, r in baseline_summary.iterrows()}
    new_counts = {r["Field Key"]: int(r["Mismatch Count"]) for _, r in result.mismatch_summary.iterrows()}
    all_keys = sorted(set(base_counts) | set(new_counts))
    for k in all_keys:
        b = base_counts.get(k, 0)
        n = new_counts.get(k, 0)
        delta = n - b
        arrow = "+" if delta > 0 else ("-" if delta < 0 else "=")
        print(f"{k:<40s} {b:>10d} {n:>10d}  {delta:>+9d} {arrow}")


if __name__ == "__main__":
    main()
