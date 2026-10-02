"""Paid Time Off is now a UZIO default: never created, still mapped.

Run:  python scratch/verify_pto_default_earning.py [unit|adp|paycom ...]

UZIO auto-creates the "Paid PTO" earning on every company, the way it already
auto-creates Regular Wage and Overtime. So the setup helper must stop creating
a Paid Time Off earning and instead list it in the earnings mapping CSV against
UZIO's name — exactly how Regular and Overtime are handled today.

Names that only look like PTO ("PTO/SIC AVAIL", "PTO Management") keep being
created: wrongly skipping one means it never exists in UZIO.
"""
import importlib.util
import glob
import io
import os
import shutil
import subprocess
import sys
import tempfile

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from apps.adp import prior_payroll_setup_helper as adp        # noqa: E402
from apps.paycom import prior_payroll_setup_helper as pay     # noqa: E402

BASELINE = "34a457f"          # main before this change
D = r"C:\Users\rohit.kaushik\Downloads"
MOSES = sorted(glob.glob(os.path.join(
    D, "Moses", "Payroll Data", "Cleaned", "*PriorPayroll*.csv")))
# Paycom prior payroll files (the shape the helper reads: Code Description /
# Type Code / Type Description). Banda Logistics carries a Paid Time Off earning.
PAYCOM_REGISTERS = sorted(glob.glob(os.path.join(
    D, "Banda Logistics", "PriorPayroll_*.csv")))

# Every PTO-ish earning description seen across the generated mapping files.
CASES = [
    ("Paid Time Off",        "Paid PTO"),
    ("PTO",                  "Paid PTO"),
    ("pto",                  "Paid PTO"),
    ("PTO Hours",            "Paid PTO"),
    ("Paid Time Off Hours",  "Paid PTO"),
    ("Paid Time Off Earnings", "Paid PTO"),
    # look like PTO, are not
    ("Pto/Sic Avail",        ""),
    ("PTO Management",       ""),
    ("Unpaid Time Off",      ""),
    ("unpaid time off",      ""),
    ("Paid Sick Leave",      ""),
    ("Sick",                 ""),
    # untouched neighbours
    ("PTO Balance Payout",   "PTO Balance Payout"),
    ("PTO Payout",           "PTO Balance Payout"),
    ("Regular",              "Regular Wage"),
    ("Overtime",             "Overtime"),
]

failures = 0


class U(io.BytesIO):
    def __init__(self, path):
        with open(path, "rb") as fh:
            super().__init__(fh.read())
        self.name = os.path.basename(path)
        self.size = len(self.getvalue())


def check(label, ok, detail=""):
    global failures
    print("   %-66s %s%s" % (label, "OK" if ok else "FAIL",
                             "" if ok else "  <- " + str(detail)[:300]))
    failures += 0 if ok else 1


def baseline_adp():
    src = subprocess.run(
        ["git", "-C", ROOT, "show", BASELINE + ":apps/adp/prior_payroll_setup_helper.py"],
        capture_output=True, text=True, encoding="utf-8", check=True).stdout
    path = os.path.join(tempfile.gettempdir(), "ppsh_adp_baseline.py")
    open(path, "w", encoding="utf-8").write(src)
    spec = importlib.util.spec_from_file_location("ppsh_adp_baseline", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- unit
def group_unit():
    print("\n== default_earning_name, both vendors")
    for mod, who in ((adp, "ADP"), (pay, "Paycom")):
        wrong = [(desc, mod.default_earning_name("", desc), want)
                 for desc, want in CASES
                 if mod.default_earning_name("", desc) != want]
        check("%s: every name lands where it should" % who, not wrong, wrong)


# ---------------------------------------------------------------- adp
def group_adp():
    print("\n== ADP, on Moses's prior payroll")
    if not MOSES:
        check("Moses prior payroll files found", False, "none")
        return
    old = baseline_adp()
    # The helper LEARNS earning codes from whatever it reads and writes them
    # into apps/adp/adp_earning_code_catalog.json. A test must not edit the
    # shipped catalog, so both modules get a throwaway copy.
    tmp_catalog = os.path.join(tempfile.gettempdir(), "adp_earning_catalog_test.json")
    shutil.copyfile(adp.ADP_EARNING_CODE_CATALOG_PATH, tmp_catalog)
    adp.ADP_EARNING_CODE_CATALOG_PATH = tmp_catalog
    old.ADP_EARNING_CODE_CATALOG_PATH = tmp_catalog

    files = [U(p) for p in MOSES]
    o_res, _ = old.run_setup_helper([U(p) for p in MOSES])
    n_res, _ = adp.run_setup_helper(files)

    def split(mod, res):
        rows, _catalog_changes = mod.adp_earnings_to_setup_rows(
            res.get("Earnings_Codes", []))
        return mod.filter_default_uzio_earnings(rows)

    o_kept, o_skip = split(old, o_res)
    n_kept, n_skip = split(adp, n_res)
    pto_desc = "Paid Time Off"

    check("baseline created a Paid Time Off earning",
          any(r["Type Description"] == pto_desc for r in o_kept),
          [r["Type Description"] for r in o_kept])
    check("it is no longer created",
          not any(r["Type Description"] == pto_desc for r in n_kept),
          [r["Type Description"] for r in n_kept])
    skipped_pto = [r for r in n_skip if r["Type Description"] == pto_desc]
    check("it is skipped as the UZIO default Paid PTO",
          len(skipped_pto) == 1 and skipped_pto[0]["UZIO Default Earning"] == "Paid PTO",
          skipped_pto)
    check("nothing else moved",
          {r["Type Description"] for r in o_kept} - {r["Type Description"] for r in n_kept}
          == {pto_desc}
          and {r["Type Description"] for r in n_kept} <= {r["Type Description"] for r in o_kept},
          ({r["Type Description"] for r in o_kept} ^ {r["Type Description"] for r in n_kept}))

    # the mapping CSV must still carry it, now against UZIO's own name
    o_map = old.build_earnings_mapping_rows(
        old.enrich_earnings_for_uzio(o_kept), o_skip)
    n_map = adp.build_earnings_mapping_rows(
        adp.enrich_earnings_for_uzio(n_kept), n_skip)
    o_by_src = {r["Source Earning Code Name"]: r["Uzio Earning Code Name"] for r in o_map}
    n_by_src = {r["Source Earning Code Name"]: r["Uzio Earning Code Name"] for r in n_map}
    check("the mapping file still lists every source earning",
          set(o_by_src) == set(n_by_src),
          set(o_by_src) ^ set(n_by_src))
    moved = {k: (o_by_src[k], n_by_src[k]) for k in o_by_src if o_by_src[k] != n_by_src[k]}
    check("only the PTO row's UZIO name changed, to Paid PTO",
          len(moved) == 1 and list(moved.values())[0][1] == "Paid PTO", moved)
    print("      %s" % list(moved.items()))


# ---------------------------------------------------------------- paycom
def group_paycom():
    print("\n== Paycom, on a prior payroll register")
    looked = 0
    for path in PAYCOM_REGISTERS:
        if not os.path.exists(path):
            continue
        looked += 1
        df = (pd.read_csv(path, dtype=str, low_memory=False)
              if path.lower().endswith(".csv") else pd.read_excel(path, dtype=str))
        earnings = pay.extract_unique_earnings_from_prior(df)
        if not earnings:
            continue
        kept, skipped = pay.filter_default_uzio_earnings(earnings)
        rows = pay.build_earnings_mapping_rows(pay.enrich_earnings_for_uzio(kept), skipped)
        names = {str(r.get("Type Description", "")).strip().lower() for r in earnings}
        ptos = [r for r in skipped
                if str(r["Type Description"]).strip().lower() in ("pto", "paid time off")]
        label = os.path.basename(path)[:34]
        if not ({"pto", "paid time off"} & names):
            print("      %-36s no PTO earning in this register" % label)
            continue
        check("%s: PTO is skipped as Paid PTO" % label,
              ptos and all(r["UZIO Default Earning"] == "Paid PTO" for r in ptos), ptos)
        check("%s: PTO is not created" % label,
              not any(str(r["Type Description"]).strip().lower() in ("pto", "paid time off")
                      for r in kept),
              [r["Type Description"] for r in kept])
        mapped = [r for r in rows if r.get("Uzio Earning Code Name") == "Paid PTO"]
        check("%s: and still appears in the mapping file" % label, bool(mapped), rows[:4])
    check("at least one Paycom register was read", looked > 0, looked)


def group_sweep():
    """Every earning name this tool has ever written, baseline vs now."""
    print("\n== every earning name across past client runs")
    names = set()
    for f in glob.glob(os.path.join(D, "**", "*arnings_mapping*.csv"), recursive=True):
        if os.path.basename(f).startswith("~$"):
            continue
        try:
            df = pd.read_csv(f, dtype=str)
        except Exception:
            continue
        for col in ("Source Earning Code Name", "Uzio Earning Code Name"):
            if col in df.columns:
                names |= {str(v).strip() for v in df[col].dropna() if str(v).strip()}
    check("collected real earning names", len(names) > 40, len(names))

    old = baseline_adp()
    moved = {n: (old.default_earning_name("", n), adp.default_earning_name("", n))
             for n in sorted(names)
             if old.default_earning_name("", n) != adp.default_earning_name("", n)}
    for n, (was, now) in moved.items():
        print("      %-46s %r -> %r" % (n[:46], was, now))
    check("only clear PTO names changed, and only to Paid PTO",
          all(now == "Paid PTO" and was == ""
              and n.strip().lower() in ("pto", "paid time off", "pto hours",
                                        "pto earnings", "paid time off hours",
                                        "paid time off earnings")
              for n, (was, now) in moved.items()),
          moved)
    check("something did change", bool(moved), moved)


GROUPS = {"unit": group_unit, "adp": group_adp, "paycom": group_paycom,
          "sweep": group_sweep}


def main(argv):
    for name in (argv or list(GROUPS)):
        try:
            GROUPS[name]()
        except Exception as e:
            check("group %s ran" % name, False, repr(e))
    print()
    print("FAIL - %d check(s)" % failures if failures else "PASS - every check held")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
