"""Verify the ADP Deduction Sanity Check on real client files.

Run:  python scratch/verify_adp_deduction_sanity.py [real|clients|moses|synthetic|ui ...]

Spec: docs/superpowers/specs/2026-10-08-adp-deduction-sanity-design.md

The tool removes ROWS only and never edits a value, so every check that
matters is "the rows that stay are byte-for-byte the rows that came in".
"""
import io
import json
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from apps.adp import deduction_sanity as ds          # noqa: E402

D = r"C:\Users\rohit.kaushik\Downloads"
REAL = [
    r"55th and 3rd\Prior Comp\Voluntary Deduction.xlsx",
    r"61 Degree\Audit Data\Voluntary Deduction.xlsx",
    r"Beck Logistics\Payroll\Deduction_Report.xlsx",
    r"BTK AutoGroup\BTK_RUSH_INC_Deduction_Report.xlsx",
    r"Cat 5\Voluntary Deduction (1).xlsx",
    r"CDC\Payroll\Deduction_Report.xlsx",
    r"East West Logistics\Voluntary Deduction.xlsx",
    r"Elite OnPoint\Data shared by Shruti\Voluntary Deduction (9).xlsx",
    r"Fass Logistics\Payroll\Voluntary Deduction.xlsx",
    r"Hansen Brothers\Voluntary Deduction.xlsx",
    r"High Distinction\Voluntary Deduction.xlsx",
    r"Innovdel\Voluntary Deduction.xlsx",
    r"J4\Voluntary Deduction.xlsx",
    r"JDW\Voluntary Deduction.xlsx",
    r"JM Parcel\Voluntary Deduction.csv",
    r"KDL LLC\Voluntary Deduction (2).xlsx",
    r"Moses\Payroll Data\Cleaned\Moses_Solutions_LLC_Deduction_Report.xlsx",
    r"North Star Parcel\Voluntary Deduction.xlsx",
    r"Travel Management\Prior Comp\Voluntary Deduction.xlsx",
]
NO_ASSOCIATE_ID = [r"Happy Delivery\Voluntary Deduction.xlsx", r"Cat 5\Cat 5_Voluntary Deduction.xlsx"]

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
    print("   %-74s %s%s" % (label, "OK" if ok else "FAIL",
                             "" if ok else "  <- " + str(detail)[:300]))
    failures += 0 if ok else 1


def short(rel):
    return rel.split("\\")[0]


# ---------------------------------------------------------------- real
def group_real():
    print("\n== every real file: rows removed only, values untouched")
    for rel in REAL:
        r, err = ds.run_sanity(up(rel))
        if err:
            check("%s reads" % short(rel), False, err)
            continue
        df, kept, removed = r["df"], r["kept"], r["removed"]
        name = short(rel)
        ok_count = len(kept) + len(removed) == len(df)
        csv_bytes = ds.corrected_csv_bytes(kept)
        back = pd.read_csv(io.BytesIO(csv_bytes), dtype=str, keep_default_na=False)
        # the kept rows, located in the source by Source Row, must be identical
        removed_src = set(removed["Source Row"])
        src_rows = [i for i in range(len(df)) if r["header_row"] + 1 + i not in removed_src]
        identical = df.iloc[src_rows].reset_index(drop=True).equals(back)
        totals_gone = not any(str(v).strip().lower().startswith("report totals")
                              for v in back.values.ravel())
        check("%s: kept + removed = source (%d + %d = %d)" % (name, len(kept), len(removed),
                                                           len(df)), ok_count)
        check("%s: CSV has no BOM, same headers, kept rows identical to source" % name,
              not csv_bytes.startswith(b"\xef\xbb\xbf") and list(back.columns) == list(df.columns)
              and identical)
        check("%s: Report Totals row removed" % name,
              totals_gone and (removed["Reason"] == ds.CAT_TOTALS).sum() == 1,
              removed["Reason"].value_counts().to_dict())
        dup_removed = removed["Reason"].str.contains("uplicate").any() if len(removed) else False
        check("%s: no row removed for being a duplicate" % name, not dup_removed)
        xlsx = ds.report_xlsx_bytes(r)
        book = pd.read_excel(io.BytesIO(xlsx), sheet_name=None, dtype=str)
        check("%s: report has the five sheets" % name,
              list(book) == ["Corrected Data", "Removed Rows", "Garnishments", "Flagged Rows",
                             "Change Log"], list(book))
        log = book["Change Log"]
        check("%s: one Change Log line per removed row" % name,
              (log["Action"] == "Row removed").sum() == len(removed))

    print("\n== files without an ASSOCIATE ID column stop")
    for rel in NO_ASSOCIATE_ID:
        r, err = ds.run_sanity(up(rel))
        check("%s: refused, naming ASSOCIATE ID" % short(rel),
              r is None and isinstance(err, dict) and err["missing"] == ["ASSOCIATE ID"], err)


# ---------------------------------------------------------------- clients
def group_clients():
    print("\n== default ticks")
    ticks = {"CHECKING": ds.CAT_DD, "SAVINGS": ds.CAT_DD, "HSA SAVINGS": None,
             "SUPPORT": ds.CAT_GARN, "GARNISHMENT%": ds.CAT_GARN, "TAX LEVY%": ds.CAT_GARN,
             "BANKRUPTCY": ds.CAT_GARN, "SPT/WAGEAGREMNT": ds.CAT_GARN,
             "Payactiv": ds.CAT_EWA, "ZayZoon DirDep": ds.CAT_EWA, "ZayZoonDirDep": ds.CAT_EWA,
             "TapCheck": ds.CAT_EWA, "REIMBURSEMENT": ds.CAT_EWA, "MILEAGE REIMB": ds.CAT_EWA,
             "ADP 401K%": None, "Med Post Tax": None, "Medical Spouse": None,
             "VOL SP LIFE": None, "Pre Paid Legal": None, "PAC": None}
    for desc, want in ticks.items():
        got = ds.default_category(desc)
        check("%-18s -> %s" % (desc, want or "not ticked"), got == want, got)

    print("\n== Innovdel: 280 descriptions with extra spaces are flagged, not trimmed")
    r, _ = ds.run_sanity(up(r"Innovdel\Voluntary Deduction.xlsx"))
    sp = r["flags"][r["flags"]["Issue"].str.startswith("Extra spaces")]
    check("280 rows flagged", len(sp) == 280, len(sp))
    check("their descriptions still carry the spaces in the CSV",
          (r["kept"]["DEDUCTION DESCRIPTION"] != r["kept"]["DEDUCTION DESCRIPTION"].str.strip())
          .sum() == 280)

    print("\n== JDW: duplicates flagged, none removed")
    r, _ = ds.run_sanity(up(r"JDW\Voluntary Deduction.xlsx"))
    dup = r["flags"][r["flags"]["Issue"].str.startswith("Duplicate")]
    ident = dup[dup["Issue"].str.contains("identical")]
    check("identical-duplicate rows flagged (%d)" % len(ident), len(ident) > 0)
    check("different-amount duplicates flagged (%d)" % (len(dup) - len(ident)),
          len(dup) > len(ident))
    check("every flagged duplicate is still in the CSV",
          set(dup["Source Row"]) <= set(range(r["header_row"] + 1,
                                              r["header_row"] + 1 + len(r["df"])))
          and not (set(dup["Source Row"]) & set(r["removed"]["Source Row"])))

    print("\n== JM Parcel: SSN-shaped Associate IDs")
    r, _ = ds.run_sanity(up(r"JM Parcel\Voluntary Deduction.csv"))
    ssn = r["flags"][r["flags"]["Issue"] == "Associate ID looks like an SSN"]
    check("flagged (%d rows)" % len(ssn), len(ssn) > 300, len(ssn))
    check("e.g. 073-08-7655 and 769350291",
          {"073-08-7655", "769350291"} <= set(ssn["ASSOCIATE ID"]))

    print("\n== KDL: negative MILEAGE REIMB is removed by default (reimbursement)")
    r, _ = ds.run_sanity(up(r"KDL LLC\Voluntary Deduction (2).xlsx"))
    check("no 'Amount is negative' left", not (r["flags"]["Issue"] == "Amount is negative").any())
    check("MILEAGE REIMB rows removed",
          (r["removed"]["DEDUCTION DESCRIPTION"] == "MILEAGE REIMB").sum() == 2)
    r2, _ = ds.run_sanity(up(r"KDL LLC\Voluntary Deduction (2).xlsx"),
                          r["remove"] - {"MILEAGE REIMB"})
    check("unticked, they stay and are flagged negative",
          (r2["flags"]["Issue"] == "Amount is negative").sum() == 2)


# ---------------------------------------------------------------- moses
def group_moses():
    print("\n== Moses: tool vs the file cleaned by hand")
    r, _ = ds.run_sanity(up(r"Moses\Payroll Data\Cleaned\Moses_Solutions_LLC_Deduction_Report.xlsx"))
    man = pd.read_csv(os.path.join(D, r"Moses\Payroll Data\Cleaned"
                                      r"\Moses_Solutions_LLC_Deduction_Report_cleaned.csv"),
                      dtype=str, keep_default_na=False)
    man = man[man["ASSOCIATE ID"].str.strip() != ""]            # hand-kept Totals line
    cols = ["ASSOCIATE ID", "DEDUCTION CODE", "DEDUCTION DESCRIPTION"]
    tool = r["kept"][cols].apply(tuple, axis=1).value_counts().sort_index()
    hand = man[cols].apply(tuple, axis=1).value_counts().sort_index()
    check("same rows kept (%d tool / %d by hand, Totals line aside)" % (len(r["kept"]), len(man)),
          tool.equals(hand))


# ---------------------------------------------------------------- synthetic
def _csv(rows, pre=None):
    head = ["COMPANY CODE", "NAME", "ASSOCIATE ID", "DEDUCTION CODE", "DEDUCTION DESCRIPTION",
            "DEDUCTION AMOUNT", "DEDUCTION %"]
    import csv as _csv_mod
    buf = io.StringIO()
    for line in pre or []:
        buf.write(line + "\n")
    w = _csv_mod.writer(buf, lineterminator="\n")
    w.writerow(head)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def group_synthetic():
    print("\n== synthetic rows, one issue each")
    rows = [
        ["X", "A, Ok", "OK1", "81", "401K%", "", "5.0000"],
        ["X", "B, Both", "BOTH1", "81", "401K%", "10.00", "5.0000"],
        ["X", "C, None", "NONE1", "81", "401K%", "", ""],
        ["X", "D, Dollar", "DOL1", "MED", "Medical", "$25.00", ""],
        ["X", "E, Pct", "PCT1", "81", "401K%", "", "150"],
        ["X", "F, Neg", "NEG1", "MED", "Medical", "-5.00", ""],
        ["X", "G, NoDesc", "ND1", "MED", "", "5.00", ""],
        ["X", "H, NoCode", "NC1", "", "Medical", "5.00", ""],
        ["X", "I, Check", "CK1", "CK1", "CHECKING", "", ""],
        ["Report Totals:", "", "", "", "", "", ""],
    ]
    r, err = ds.run_sanity(up(_csv(rows, pre=["ADP Voluntary Deduction", ""]), "s.csv"))
    check("reads with two preamble rows (one blank)", err is None and r["header_row"] == 3,
          err or r["header_row"])
    issues = {aid: set(g["Issue"]) for aid, g in r["flags"].groupby("ASSOCIATE ID")}
    want = {"BOTH1": "Amount and % are both filled (the API takes only one)",
            "NONE1": "Amount and % are both blank",
            "DOL1": "Amount is not a plain number (e.g. a $ or % sign)",
            "PCT1": "% is outside 0-100", "NEG1": "Amount is negative",
            "ND1": "Deduction description is blank", "NC1": "Deduction code is blank"}
    for aid, issue in want.items():
        check("%s flagged: %s" % (aid, issue[:40]), issue in issues.get(aid, set()),
              issues.get(aid))
    check("the clean row is not flagged", "OK1" not in issues)
    check("CHECKING removed, Totals removed",
          sorted(r["removed"]["Reason"]) == sorted([ds.CAT_DD, ds.CAT_TOTALS]))
    log = ds.change_log(r)
    check("Change Log records the preamble removal",
          log.iloc[0]["Action"] == "Rows above the header removed")
    back = pd.read_csv(io.BytesIO(ds.corrected_csv_bytes(r["kept"])), dtype=str,
                       keep_default_na=False)
    check("'$25.00' and '150' written back unchanged",
          "$25.00" in set(back["DEDUCTION AMOUNT"]) and "150" in set(back["DEDUCTION %"]))
    check("CSV starts at the header", back.columns[0] == "COMPANY CODE")

    print("\n== a cp1252 CSV")
    data = _csv([["X", "Peña, José", "OK1", "81", "401K%", "", "5"]]).decode().encode("cp1252")
    r, err = ds.run_sanity(up(data, "cp.csv"))
    check("reads, name intact", err is None and r["kept"].iloc[0]["NAME"] == "Peña, José", err)


# ---------------------------------------------------------------- ui
def group_ui():
    print("\n== the screen")
    from streamlit.testing.v1 import AppTest

    def script():
        import io as _io
        import json as _json
        import os as _os
        import sys as _sys
        _sys.path.insert(0, _os.environ["DS_ROOT"])
        import streamlit as _st
        from apps.adp import deduction_sanity
        files = _json.loads(_os.environ.get("DS_FILES", "{}"))

        class _U(_io.BytesIO):
            def __init__(self, p):
                with open(p, "rb") as fh:
                    super().__init__(fh.read())
                self.name = _os.path.basename(p)
                self.size = len(self.getvalue())

        _st.file_uploader = lambda *a, **k: (_U(files[k["key"]]) if k.get("key") in files
                                             else None)
        deduction_sanity.render_ui()

    os.environ["DS_ROOT"] = ROOT
    jdw = os.path.join(D, r"JDW\Voluntary Deduction.xlsx")
    os.environ["DS_FILES"] = json.dumps({"adp_ded_sanity_upload": jdw})
    at = AppTest.from_function(script, default_timeout=180).run()
    check("no exception", not at.exception, [e.value for e in at.exception])
    ck = {c.label.split("**")[1]: c for c in at.checkbox}
    check("CHECKING and SUPPORT start ticked, ADP 401K% does not",
          ck["CHECKING"].value and ck["SUPPORT"].value and not ck["ADP 401K%"].value,
          {k: c.value for k, c in ck.items()})
    check("two download buttons", len(at.get("download_button")) == 2)
    check("red 'Needs your attention' shown (JDW has duplicates)",
          any("Needs your attention" in m.value for m in at.markdown))
    before = int(at.metric[0].value)
    ck["CHECKING"].uncheck().run()
    after = int(at.metric[0].value)
    check("unticking CHECKING keeps its rows (%d -> %d kept)" % (before, after), after > before)

    os.environ["DS_FILES"] = json.dumps(
        {"adp_ded_sanity_upload": os.path.join(D, NO_ASSOCIATE_ID[0])})
    at = AppTest.from_function(script, default_timeout=180).run()
    check("missing column: red box, no downloads",
          any("Required column missing" in m.value for m in at.markdown)
          and not at.get("download_button"))


GROUPS = {"real": group_real, "clients": group_clients, "moses": group_moses,
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
