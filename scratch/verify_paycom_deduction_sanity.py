"""Verify the Paycom Deduction Sanity Check on real client files.

Run:  python scratch/verify_paycom_deduction_sanity.py [rules|real|manual|synthetic|ui ...]

Spec: docs/superpowers/specs/2026-10-08-paycom-deduction-sanity-design.md

Every real-file check runs with a FIXED "today" so the Stop Date cutoff does
not move under the test.
"""
import glob
import io
import json
import os
import sys
from datetime import date

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from apps.paycom import deduction_sanity as ps          # noqa: E402

D = r"C:\Users\rohit.kaushik\Downloads"
TODAY = date(2026, 10, 8)
BANDA = r"Banda Logistics\20260930081113_Employee_Scheduled_Deductions_24a499da.csv"
BANDA_HAND = r"Banda Logistics\20260930081113_Employee_Scheduled_Deductions_24a499da - Copy.csv"
CHIEF = r"Chief Delivery\20260527033627_Employee_Scheduled_Deductions_3f0824bc.csv"
SPELMAN = r"Spelman\20260713054130_Employee_Scheduled_Deductions_70c86027.csv"
STAVE = r"Stave Delivery\Prior Payroll\Prior Payroll\Stave Delivery_Employee_Scheduled_Deductions_.csv"

failures = 0


class U(io.BytesIO):
    def __init__(self, data, name):
        super().__init__(data)
        self.name = name
        self.size = len(data)


def up(rel_or_bytes, name=None):
    if isinstance(rel_or_bytes, bytes):
        return U(rel_or_bytes, name or "upload.csv")
    p = os.path.join(D, rel_or_bytes)
    return U(open(p, "rb").read(), os.path.basename(p))


def check(label, ok, detail=""):
    global failures
    print("   %-76s %s%s" % (label, "OK" if ok else "FAIL",
                             "" if ok else "  <- " + str(detail)[:300]))
    failures += 0 if ok else 1


def real_files():
    return sorted(os.path.relpath(f, D)
                  for f in glob.glob(D + r"\**\*Scheduled_Deduction*", recursive=True)
                  if "Claude Core" not in f)


# ---------------------------------------------------------------- rules
def group_rules():
    print("\n== zero rule (Rohit's table)")
    for amt, pct, gone in (("0", "10", False), ("100", "0", False), ("", "0", True),
                           ("0", "", True), ("0", "0", True), ("", "", True),
                           ("0.00", "0.000000", True), ("5.87", "", False), ("", "0.04", False)):
        z = ps._is_zero_or_blank(amt) and ps._is_zero_or_blank(pct)
        check("Amount %-6r Percent %-10r -> %s" % (amt, pct, "removed" if gone else "kept"),
              z == gone)

    print("\n== Stop Date cutoff (today %s -> before %s)" % (TODAY, ps.month_cutoff(TODAY)))
    cut = ps.month_cutoff(TODAY)
    for stop, gone in (("9/30/2026", True), ("10/1/2026", False), ("10/05/2026", False),
                       ("12/31/2026", False), ("00/00/0000", False), ("", False),
                       ("1/1/2025", True)):
        d = ps.parse_mdy(stop)
        check("Stop %-11r -> %s" % (stop, "removed" if gone else "kept"),
              (d is not None and d < cut) == gone)

    print("\n== percent x 100")
    for v, want in (("0.04", "4"), ("0.040000", "4"), ("0.00432", "0.432"), ("0.0745", "7.45"),
                    ("1.72385", "172.385"), ("0.5", "50"), ("", ""), ("abc", "abc")):
        check("%-10r -> %r" % (v, want), ps.scale_percent(v) == want, ps.scale_percent(v))

    print("\n== default ticks")
    for desc, want in (("Child Support $", ps.CAT_GARN), ("SUPPORT ORDER $ 1", ps.CAT_GARN),
                       ("ANNUAL SUPPORT FEE $", ps.CAT_GARN), ("GARN % 1", ps.CAT_GARN),
                       ("NEW YORK GARNISHMENT %", ps.CAT_GARN), ("TAX LEVY % 1", ps.CAT_GARN),
                       ("BANKRUPTCY $", ps.CAT_GARN), ("WAGE ASSIGNMENT % 1 - MED", ps.CAT_GARN),
                       ("WAGE ASSIGN $ 1", ps.CAT_GARN), ("Lien", ps.CAT_GARN),
                       ("Cell Phone Reimbursement", ps.CAT_EWA), ("Tuition Reimburse", ps.CAT_EWA),
                       ("Employer Health Insurance Reim", ps.CAT_EWA),
                       ("Earned Wage Access", ps.CAT_EWA), ("TapCheck", ps.CAT_EWA),
                       ("ZayZoon DirDep", ps.CAT_EWA), ("Payactiv", ps.CAT_EWA),
                       ("LOA Benefits Reimb", None), ("LOA FSA Reimb", None),
                       ("LOA Medical Reimb", None), ("401K % Retirement", None),
                       ("Health Savings", None), ("Medical", None), ("Pay Advance", None),
                       ("401K Loan 1", None)):
        got = ps.default_category(desc)
        check("%-32s -> %s" % (desc, want or "not ticked"), got == want, got)


# ---------------------------------------------------------------- real
def group_real():
    print("\n== every real Paycom file")
    for rel in real_files():
        name = rel[:48]
        r, err = ps.run_sanity(up(rel), today=TODAY)
        if err:
            check("%s reads" % name, False, err)
            continue
        df, kept, removed, cols = r["df"], r["kept"], r["removed"], r["cols"]
        csv_bytes = ps.corrected_csv_bytes(kept)
        back = pd.read_csv(io.BytesIO(csv_bytes), dtype=str, keep_default_na=False)
        src = df.loc[[i for i in df.index if i not in set(removed.index.tolist())]]
        source_kept = df.iloc[[s - r["header_row"] - 1 for s in r["kept_src"]]].reset_index(drop=True)
        pc = cols[ps.COL_PCT]
        other = [c for c in df.columns if c != pc]
        same_other = source_kept[other].equals(back[other])
        if r["multiply_percent"]:
            pct_ok = all(back[pc][i] == ps.scale_percent(source_kept[pc][i]) for i in range(len(back)))
        else:
            pct_ok = source_kept[pc].equals(back[pc])
        stop_ok = all(not (ps.parse_mdy(v) and ps.parse_mdy(v) < r["cutoff"]) for v in back[cols[ps.COL_STOP]])
        zero_ok = not any(ps._is_zero_or_blank(a) and ps._is_zero_or_blank(p)
                          for a, p in zip(back[cols[ps.COL_AMT]], back[pc]))
        check("%s: kept + removed = source" % name, len(kept) + len(removed) == len(df))
        check("%s: no BOM, same headers, non-%% cells untouched" % name,
              not csv_bytes.startswith(b"\xef\xbb\xbf") and list(back.columns) == list(df.columns)
              and same_other)
        check("%s: Percent %s" % (name, "x100 exactly" if r["multiply_percent"] else "untouched"),
              pct_ok)
        check("%s: no passed Stop Date, no all-zero row left" % name, stop_ok and zero_ok)
        log = ps.change_log(r)
        check("%s: Change Log = removed rows + %% changes" % name,
              (log["Action"] == "Row removed").sum() == len(removed)
              and (log["Action"] == "Value changed").sum() == len(r["pct_changes"]))

    print("\n== percent format detected per file")
    for rel, frac in ((BANDA, True), (STAVE, True), (CHIEF, False), (SPELMAN, False)):
        r, _ = ps.run_sanity(up(rel), today=TODAY)
        check("%s -> %s" % (rel.split("\\")[0], "fraction (x100)" if frac else "whole (left)"),
              r["is_fraction"] == frac and (len(r["pct_changes"]) > 0) == frac)
    r, _ = ps.run_sanity(up(CHIEF), today=TODAY, multiply_percent=True)
    check("Chief, override ticked -> its 5% would become 500 and is flagged",
          (r["flags"]["Issue"] == "Percent is outside 0-100").any())


# ---------------------------------------------------------------- manual
def group_manual():
    print("\n== Banda: tool vs the file cleaned by hand (same day, 05-Oct-2026)")
    r, _ = ps.run_sanity(up(BANDA), today=date(2026, 10, 5))
    hand = pd.read_csv(os.path.join(D, BANDA_HAND), dtype=str, keep_default_na=False)
    cols = ["EE Code", "Deduction Code", "Deduction Desc", "Amount"]
    tool = r["kept"][cols].apply(tuple, axis=1).value_counts().sort_index()
    by_hand = hand[cols].apply(tuple, axis=1).value_counts().sort_index()
    check("same rows kept (%d tool / %d by hand)" % (len(r["kept"]), len(hand)), tool.equals(by_hand))
    j = r["kept"].merge(hand, on=cols, suffixes=("_t", "_h"))
    check("same Percent on every kept row (%d with a %%)" % (j["Percent_t"] != "").sum(),
          all(ps._num(a) == ps._num(b) for a, b in zip(j["Percent_t"], j["Percent_h"])))


# ---------------------------------------------------------------- synthetic
HEAD = ["EE Code", "EE Name", "Deduction Code", "Deduction Desc", "Amount", "Percent",
        "Tax Treatment", "Limit", "Limit Accum", "Company Match", "Start Date", "Stop Date"]


def _csv(rows):
    import csv as _c
    buf = io.StringIO()
    w = _c.writer(buf, lineterminator="\n")
    w.writerow(HEAD)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def group_synthetic():
    print("\n== synthetic rows, one issue each")
    A = "A - After Tax Deduction"
    rows = [
        ["OK1", "Ok", "MED", "Medical", "25.00", "", A, "No", "0", "No", "1/1/2026", "00/00/0000"],
        ["BOTH", "Both", "K4P", "401K % Retirement", "0", "0.10", "H - FICA", "No", "0", "No", "", "00/00/0000"],
        ["TAX0", "NoTax", "MED", "Medical", "5", "", "", "No", "0", "No", "", "00/00/0000"],
        ["TAXX", "BadTax", "MED", "Medical", "5", "", "After Tax", "No", "0", "No", "", "00/00/0000"],
        ["DATE", "BadDate", "MED", "Medical", "5", "", A, "No", "0", "No", "2026-01-01", "00/00/0000"],
        ["THIS", "ThisMonth", "MED", "Medical", "5", "", A, "No", "0", "No", "00/00/0000", "10/05/2026"],
        ["LIM", "BadLimit", "MED", "Medical", "5", "", A, "Yes 500", "x", "No", "", "00/00/0000"],
        ["SPC", "Spaced", "MED", "Medical", "5", "", A, "No", "0", " []", "", "00/00/0000"],
        ["OLD", "Stopped", "MED", "Medical", "5", "", A, "No", "0", "No", "", "9/30/2026"],
        ["ZERO", "Zero", "MED", "Medical", "0", "", A, "No", "0", "No", "", "00/00/0000"],
        ["CS", "Support", "CS1", "Child Support $", "50", "", A, "No", "0", "No", "", "00/00/0000"],
    ]
    r, err = ps.run_sanity(up(_csv(rows), "s.csv"), today=TODAY)
    check("reads", err is None, err)
    issues = {eid: set(g["Issue"]) for eid, g in r["flags"].groupby("EE Code")}
    want = {
        "BOTH": "Amount and Percent are both filled (the API takes only one)",
        "TAX0": "Tax Treatment is blank",
        "TAXX": "Tax Treatment does not start with a code such as 'A -' or 'B -'",
        "DATE": "Start Date is not MM/DD/YYYY",
        "THIS": "Stop Date is before the Start Date (a blank Start Date counts as today)",
        "LIM": "Limit is not 'No' or 'Yes (amount)'",
        "SPC": "Extra spaces around Company Match",
    }
    for eid, issue in want.items():
        check("%s flagged: %s" % (eid, issue[:46]), issue in issues.get(eid, set()), issues.get(eid))
    check("LIM: Limit Accum 'x' flagged", "Limit Accum is not a number" in issues.get("LIM", set()))
    check("OK1 not flagged", "OK1" not in issues)
    check("BOTH (0 + 10%) kept, and its 0.10 became 10",
          r["kept"].set_index("EE Code").loc["BOTH", "Percent"] == "10")
    reasons = dict(zip(r["removed"]["EE Code"], r["removed"]["Reason"]))
    check("OLD removed (Stop 9/30/2026)", reasons.get("OLD") == ps.CAT_STOPPED, reasons)
    check("ZERO removed", reasons.get("ZERO") == ps.CAT_ZERO, reasons)
    check("CS removed as garnishment and listed on the Garnishments sheet",
          reasons.get("CS") == ps.CAT_GARN and
          "CS" in set(pd.read_excel(io.BytesIO(ps.report_xlsx_bytes(r)), sheet_name="Garnishments",
                                    dtype=str)["EE Code"]))
    check("THIS kept (Stop Date inside the current month)", "THIS" in set(r["kept"]["EE Code"]))

    print("\n== a required column missing")
    bad = pd.read_csv(io.BytesIO(_csv(rows)), dtype=str).drop(columns=["Tax Treatment"])
    r, err = ps.run_sanity(up(bad.to_csv(index=False).encode(), "b.csv"), today=TODAY)
    check("refused, naming Tax Treatment", r is None and err["missing"] == ["Tax Treatment"], err)


# ---------------------------------------------------------------- ui
def group_ui():
    print("\n== the screen")
    from streamlit.testing.v1 import AppTest

    def script():
        import io as _io
        import json as _json
        import os as _os
        import sys as _sys
        _sys.path.insert(0, _os.environ["PD_ROOT"])
        import streamlit as _st
        from apps.paycom import deduction_sanity
        files = _json.loads(_os.environ.get("PD_FILES", "{}"))

        class _U(_io.BytesIO):
            def __init__(self, p):
                with open(p, "rb") as fh:
                    super().__init__(fh.read())
                self.name = _os.path.basename(p)
                self.size = len(self.getvalue())

        _st.file_uploader = lambda *a, **k: (_U(files[k["key"]]) if k.get("key") in files
                                             else None)
        deduction_sanity.render_ui()

    os.environ["PD_ROOT"] = ROOT
    os.environ["PD_FILES"] = json.dumps({"paycom_ded_sanity_upload": os.path.join(D, BANDA)})
    at = AppTest.from_function(script, default_timeout=180).run()
    check("no exception", not at.exception, [e.value for e in at.exception])
    pct = [c for c in at.checkbox if "Multiply Percent" in c.label]
    check("Banda: 'Multiply Percent by 100' starts ticked", len(pct) == 1 and pct[0].value)
    ck = {c.label.split("**")[1]: c for c in at.checkbox if c.label.startswith("**")}
    check("Cell Phone Reimbursement ticked, 401K % Retirement not",
          ck["Cell Phone Reimbursement"].value and not ck["401K % Retirement"].value)
    check("two download buttons", len(at.get("download_button")) == 2)
    x100 = int(at.metric[2].value)
    pct[0].uncheck().run()
    check("unticking the %% box: no values changed (%d -> %d)" % (x100, int(at.metric[2].value)),
          x100 > 0 and int(at.metric[2].value) == 0)

    os.environ["PD_FILES"] = json.dumps({"paycom_ded_sanity_upload": os.path.join(D, CHIEF)})
    at = AppTest.from_function(script, default_timeout=180).run()
    pct = [c for c in at.checkbox if "Multiply Percent" in c.label]
    check("Chief (whole percents): the box starts unticked", len(pct) == 1 and not pct[0].value)


GROUPS = {"rules": group_rules, "real": group_real, "manual": group_manual,
          "synthetic": group_synthetic, "ui": group_ui}


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
