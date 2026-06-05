"""End-to-end check of the UZIO Add-Deduction column enrichment.

Runs the Chief Delivery prior payroll file through extract -> bifurcate ->
classify -> enrich, then builds the 3-tab xlsx and re-reads the Deductions tab
to confirm every UZIO form-field column is present with the rule-correct values.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from apps.paycom.prior_payroll_setup_helper import (
    extract_unique_deductions_from_prior,
    filter_default_uzio_deductions,
    bifurcate_match_memo,
    classify_pre_post_from_calc_description,
    enrich_deductions_for_uzio,
    extract_unique_earnings_from_prior,
    build_3tab_setup_xlsx,
    DEDUCTION_OUTPUT_COLUMNS,
)

PATH = r"C:\Users\rohit.kaushik\Downloads\Chief Delivery\payroll\PriorPayroll_12212025_03142026_03202026.csv"
OUT  = r"C:\Users\rohit.kaushik\Downloads\Chief Delivery\REBUILD_UZIO_Columns.xlsx"

df = pd.read_csv(PATH, dtype=str)
earnings = extract_unique_earnings_from_prior(df)
all_deds = extract_unique_deductions_from_prior(df)
kept, skipped = filter_default_uzio_deductions(all_deds)
contribs, deds = bifurcate_match_memo(kept)
deds = classify_pre_post_from_calc_description(df, deds)

# Simulate "Select All = Yes" for benefit types.
preview = enrich_deductions_for_uzio(deds)
benefit_tds = [r["Type Description"] for r in preview if r.get("Is Benefit Type")]
auto_sync_map = {td: "Yes" for td in benefit_tds}
enriched = enrich_deductions_for_uzio(deds, auto_sync_map)

print(f"Benefit-type deductions ({len(benefit_tds)}): {benefit_tds}\n")

cols = ["Type Code", "UZIO Master Deductions List", "UZIO Method",
        "Auto-Sync from Uzio Benefits", "Assign to all employees",
        "Track arrears", "Arrears Processing Method", "Deduction Schedule"]
print("Per-deduction field values:")
hdr = "  " + " | ".join(f"{c[:22]:<22s}" for c in cols)
print(hdr)
print("  " + "-" * (len(hdr)))
for r in enriched:
    print("  " + " | ".join(f"{str(r.get(c,'')):<22s}" for c in cols))

# Rule assertions
print("\nRule checks:")
ok = True
for r in enriched:
    benefit = r.get("Is Benefit Type")
    master_l = (r["UZIO Master Deductions List"] or "").lower()
    if benefit:
        assert r["Track arrears"] == "Yes", f"benefit {r['Type Code']} arrears!=Yes"
        assert r["Arrears Processing Method"] == "Total Amount", f"benefit {r['Type Code']} arrears method"
        assert r["Auto-Sync from Uzio Benefits"] == "Yes", f"benefit {r['Type Code']} autosync"
    else:
        assert r["Track arrears"] == "No", f"non-benefit {r['Type Code']} arrears!=No"
        assert r["Arrears Processing Method"] == "", f"non-benefit {r['Type Code']} arrears method not blank"
        assert r["Auto-Sync from Uzio Benefits"] == "N/A", f"non-benefit {r['Type Code']} autosync!=N/A"
    if master_l in {"med claim reimbursement", "med plus premium", "health cues", "health cues premium"}:
        assert r["Assign to all employees"] == "Yes", f"{r['Type Code']} assign-all should be locked Yes"
print("  All per-row rule assertions passed.")

# Build + re-read
data = build_3tab_setup_xlsx(earnings=earnings, deductions=enriched, contributions=contribs)
with open(OUT, "wb") as f:
    f.write(data)
print(f"\nWrote {OUT} ({len(data):,} bytes)")

sub = pd.read_excel(OUT, sheet_name="Deductions", dtype=str)
print(f"\nDeductions tab columns ({len(sub.columns)}): {list(sub.columns)}")
assert list(sub.columns) == DEDUCTION_OUTPUT_COLUMNS, "column order mismatch vs DEDUCTION_OUTPUT_COLUMNS"
print("Column order matches DEDUCTION_OUTPUT_COLUMNS. OK.")
