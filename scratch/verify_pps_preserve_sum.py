"""Verify that Preserve Pay Periods ADDS same-pay-date rows instead of keeping the larger.

Run:  python scratch/verify_pps_preserve_sum.py [real|unit ...]

The old module is loaded from a PINNED commit (c125408, main before this fix),
never from HEAD.
"""
import importlib.util
import io
import os
import subprocess
import sys
import tempfile

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from apps.adp import prior_payroll_sanity as new          # noqa: E402

BASELINE = "c125408"
D = r"C:\Users\rohit.kaushik\Downloads"
FILES = ["Payroll History (1).xlsx", "Payroll History (3).xlsx", "Payroll History (5).xlsx",
         r"55th and 3rd\Prior Comp\55th and 3rd_Payroll History.xlsx"]

failures = 0


def check(label, ok, detail=""):
    global failures
    print("   %-76s %s%s" % (label, "OK" if ok else "FAIL",
                             "" if ok else "  <- " + str(detail)[:300]))
    failures += 0 if ok else 1


class U(io.BytesIO):
    def __init__(self, p):
        super().__init__(open(p, "rb").read())
        self.name = os.path.basename(p)
        self.size = len(self.getvalue())


def baseline():
    src = subprocess.run(["git", "-C", ROOT, "show", BASELINE + ":apps/adp/prior_payroll_sanity.py"],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    path = os.path.join(tempfile.gettempdir(), "pps_baseline.py")
    open(path, "w", encoding="utf-8").write(src)
    spec = importlib.util.spec_from_file_location("pps_baseline", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load(rel):
    df = new.read_input_file(U(os.path.join(D, rel)))
    df = df[0] if isinstance(df, tuple) else df
    df = new.drop_summary_rows(df)
    df = df[0] if isinstance(df, tuple) else df
    eid = new._find_col(df, ["Associate ID"])
    return df[df[eid].notna() & (df[eid].astype(str).str.strip() != "")].reset_index(drop=True)


def total(df, col):
    return round(sum(new._to_float(v) or 0.0 for v in df[col]), 2)


def money_columns(df):
    """Columns that are all numbers / blanks, minus the ones merged by 'first value'."""
    skip = {new._find_col(df, [n]) for n in
            ["Associate ID", "Pay Date", "Period Ending Date", "Period Beginning Date",
             "Check/Voucher Number", "File Number", "Position ID", "Tax ID", "Dist #"]} - {None}
    out = []
    for c in df.columns:
        if c in skip:
            continue
        vals = [v for v in df[c] if not new._is_blank(v)]
        if vals and all(new._to_float(v) is not None for v in vals):
            out.append(c)
    return out


# ---------------------------------------------------------------- real
def group_real():
    old = baseline()
    for rel in FILES:
        print("\n== %s" % rel)
        df = load(rel)
        before, ev_old = old.merge_duplicate_pay_periods(df)
        after, ev_new = new.merge_duplicate_pay_periods(df)
        full, _ = new.aggregate_by_associate(df)
        cols = money_columns(df)
        lost_new = {c: round(total(df, c) - total(after, c), 2) for c in cols}
        lost_old = {c: round(total(df, c) - total(before, c), 2) for c in cols}
        bad = {c: v for c, v in lost_new.items() if abs(v) > 0.011}
        check("same groups merged as before (%d), same row count (%d)" % (len(ev_new), len(after)),
              len(ev_new) == len(ev_old) and len(after) == len(before))
        check("every one of %d money/hours/tax columns keeps the source total" % len(cols),
              not bad, bad)
        diff_full = {c: (total(after, c), total(full, c)) for c in cols
                     if abs(total(after, c) - total(full, c)) > 0.011}
        check("Preserve totals = Full Quarter totals", not diff_full, list(diff_full.items())[:3])
        for c in ("GROSS PAY", "FEDERAL INCOME - EMPLOYEE TAX"):
            if c in df.columns:
                print("      %-32s source %12.2f | before %12.2f (lost %9.2f) | after %12.2f"
                      % (c, total(df, c), total(before, c), lost_old[c], total(after, c)))
        # rows that were never duplicated are untouched
        key = lambda d: d[new._find_col(d, ["Associate ID"])].astype(str) + "|" + \
            d[new._find_col(d, ["Pay Date"])].astype(str) + "|" + \
            d[new._find_col(d, ["Period Ending Date"])].astype(str)
        merged_keys = {"%s|%s" % (e["Employee ID"], e["Pay Date"]) for e in ev_new}
        a = after[~key(after).map(lambda k: "|".join(k.split("|")[:2]) in merged_keys)]
        b = before[~key(before).map(lambda k: "|".join(k.split("|")[:2]) in merged_keys)]
        check("rows outside the merged groups identical to before (%d rows)" % len(a),
              a.reset_index(drop=True).astype(str).equals(b.reset_index(drop=True).astype(str)))

    print("\n== the examples from the investigation")
    df = load("Payroll History (1).xlsx")
    after, _ = new.merge_duplicate_pay_periods(df)
    r = after[(after["ASSOCIATE ID"].astype(str) == "F5Y5UBOMB") & (after["PAY DATE"].astype(str) == "04/10/2026")]
    check("F5Y5UBOMB 04/10/2026: one row, GROSS 615.17 + 1684.08 = 2299.25",
          len(r) == 1 and abs(new._to_float(r.iloc[0]["GROSS PAY"]) - 2299.25) < 0.005,
          r["GROSS PAY"].tolist())
    r = after[(after["ASSOCIATE ID"].astype(str) == "THR87JG7B") & (after["PAY DATE"].astype(str) == "04/24/2026")]
    check("THR87JG7B (skeleton + detail): GROSS 1094.34, state UT, real check no. kept",
          len(r) == 1 and abs(new._to_float(r.iloc[0]["GROSS PAY"]) - 1094.34) < 0.005
          and str(r.iloc[0]["WORKED IN STATE"]).strip() == "UT"
          and str(r.iloc[0]["CHECK/VOUCHER NUMBER"]).strip() == "00170180",
          r[["GROSS PAY", "WORKED IN STATE", "CHECK/VOUCHER NUMBER"]].values.tolist())
    df = load(r"55th and 3rd\Prior Comp\55th and 3rd_Payroll History.xlsx")
    after, _ = new.merge_duplicate_pay_periods(df)
    r = after[(after["ASSOCIATE ID"].astype(str) == "RZU4K8KU4") & (after["PAY DATE"].astype(str) == "03/06/2026")]
    check("RZU4K8KU4 (two checks, 55th & 3rd): GROSS 44.00 + 145.20 = 189.20",
          len(r) == 1 and abs(new._to_float(r.iloc[0]["GROSS PAY"]) - 189.20) < 0.005,
          r["GROSS PAY"].tolist())


# ---------------------------------------------------------------- unit
def group_unit():
    print("\n== merge rules on a small frame")
    cols = ["ASSOCIATE ID", "NAME", "PERIOD BEGINNING DATE", "PERIOD ENDING DATE", "PAY DATE",
            "CHECK/VOUCHER NUMBER", "WORKED IN STATE", "GROSS PAY", "REGULAR HOURS", "MEMO : X"]
    rows = [
        ["A1", "Ann", "01/01/2026", "01/14/2026", "01/20/2026", "00000000", "UT", 100.0, 10.0, "-"],
        ["A1", "Ann", "01/01/2026", "01/14/2026", "01/20/2026", "00012345", "", 50.5, 5.0, "-"],
        ["B2", "Bob", "01/01/2026", "01/14/2026", "01/20/2026", "00011111", "UT", 80.0, 8.0, 3.0],
        ["B2", "Bob", "01/01/2026", "01/14/2026", "01/20/2026", "00011111", "UT", 80.0, 8.0, 3.0],
        ["C3", "Cat", "01/01/2026", "01/14/2026", "01/20/2026", "00022222", "UT", 0.0, "-", "-"],
        ["C3", "Cat", "01/01/2026", "01/14/2026", "01/20/2026", "00022223", "UT", 70.0, 7.0, "-"],
        ["D4", "Dan", "01/01/2026", "01/14/2026", "01/20/2026", "00033333", "UT", 60.0, 6.0, "-"],
    ]
    df = pd.DataFrame(rows, columns=cols)
    out, ev = new.merge_duplicate_pay_periods(df)
    o = out.set_index("ASSOCIATE ID")
    check("two real rows are added: GROSS 150.50, hours 15", o.loc["A1", "GROSS PAY"] == 150.5
          and o.loc["A1", "REGULAR HOURS"] == 15.0, o.loc["A1"].to_dict())
    check("first real check number kept (00012345, not 00000000)",
          o.loc["A1", "CHECK/VOUCHER NUMBER"] == "00012345")
    check("state: first filled value (UT)", o.loc["A1", "WORKED IN STATE"] == "UT")
    check("a column dash on every row stays '-'", o.loc["A1", "MEMO : X"] == "-")
    check("an exact repeated row is counted once: GROSS 80, MEMO 3",
          o.loc["B2", "GROSS PAY"] == 80.0 and o.loc["B2", "MEMO : X"] == 3.0, o.loc["B2"].to_dict())
    check("the merge event says 1 exact copy dropped for B2",
          [e["Exact copies dropped"] for e in ev if e["Employee ID"] == "B2"] == [1])
    check("skeleton + detail: 0 + 70 = 70, hours '-' + 7 = 7",
          o.loc["C3", "GROSS PAY"] == 70.0 and o.loc["C3", "REGULAR HOURS"] == 7.0)
    check("a row with no duplicate is untouched", o.loc["D4"].tolist() ==
          ["Dan", "01/01/2026", "01/14/2026", "01/20/2026", "00033333", "UT", 60.0, 6.0, "-"])
    check("4 rows out, 3 merge events", len(out) == 4 and len(ev) == 3)
    check("_smart_merge_value is gone", not hasattr(new, "_smart_merge_value"))


GROUPS = {"unit": group_unit, "real": group_real}


def main(argv):
    for name in (argv or list(GROUPS)):
        try:
            GROUPS[name]()
        except Exception as e:
            import traceback
            traceback.print_exc()
            check("group %s ran" % name, False, repr(e))
    print()
    print("FAIL - %d check(s)" % failures if failures else "PASS - every check held")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
