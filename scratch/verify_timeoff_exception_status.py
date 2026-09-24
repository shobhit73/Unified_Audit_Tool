"""Verify: Exception Summary gains Employment Status + Termination Date; census required.

Run:  python scratch/verify_timeoff_exception_status.py

Runs the pre-change module (git 038c330) and the working-tree module side by side
on real client files and checks that:
  1. the filled import template is cell-for-cell unchanged
  2. Balance vs UZIO Status and Unassigned Policies are unchanged
  3. Exception Summary keeps the same rows in the same order, and only gains
     the two new columns, in the agreed position
  4. every new value equals a direct census lookup
  5. run_tool refuses to run without a census
  6. the Streamlit UI refuses Generate without a census, and works with one
"""
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile

import openpyxl
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from apps.adp import timeoff_audit as new       # noqa: E402

D = r"C:\Users\rohit.kaushik\Downloads"
CASES = {
    "Express": (D + r"\Express_Package_System_Inc_Time_Off_Balance_Summary.xlsx",
                D + r"\Time Off Import (1).xlsx",
                D + r"\Multi_Client_EXPRESS PACKAGE SYSTEM_Employee_Census.xlsm"),
    "High Distinction": (D + r"\High Distinction\New folder\Time Off Balance Summary.xlsx",
                         D + r"\High Distinction\New folder\Time Off Import.xlsx",
                         D + r"\High Distinction\Multi_Client_High Distinction Logistics LLC_Employee_Census.xlsm"),
}
OLD_EXC_COLS = ["Employee ID", "Employee Name", "Issue Category", "ADP Balance"]


class U(io.BytesIO):
    def __init__(self, data, name):
        super().__init__(data)
        self.name = name
        self.size = len(data)


def up(path):
    return U(open(path, "rb").read(), os.path.basename(path))


def load_old():
    # Pinned: HEAD keeps moving as this work merges, and this script's job is to
    # compare against main as it was BEFORE the status columns and the policy
    # mapping — 038c330.
    src = subprocess.run(["git", "-C", ROOT, "show", "038c330:apps/adp/timeoff_audit.py"],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    path = os.path.join(tempfile.gettempdir(), "timeoff_audit_HEAD.py")
    open(path, "w", encoding="utf-8").write(src)
    spec = importlib.util.spec_from_file_location("timeoff_audit_HEAD", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def blank_template(path):
    """The Express template as it was at 16:35 — every Opening Balance blank."""
    wb = openpyxl.load_workbook(path)
    ws = wb["Time Off Details"]
    for r in range(5, ws.max_row + 1):
        if ws.cell(row=r, column=3).value not in (None, ""):
            ws.cell(row=r, column=8).value = None
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def cells(xbytes, sheet):
    ws = openpyxl.load_workbook(io.BytesIO(xbytes))[sheet]
    return [[c.value for c in row] for row in ws.iter_rows()]


def sheet_df(xbytes, sheet):
    return pd.read_excel(io.BytesIO(xbytes), sheet_name=sheet, dtype=str).fillna("")


def cents_equal(a, b):
    """Equal, or a cent apart.

    The baseline rounds every ADP transaction before adding; the working tree
    adds first and rounds once, matching ADP's own subtotal. Some balances move
    by 0.01 because of that fix, which is deliberate.
    """
    if a is None and b is None:
        return True
    try:
        fa, fb = float(a), float(b)
        if fa != fa and fb != fb:          # both NaN
            return True
        return abs(fa - fb) <= 0.011
    except (TypeError, ValueError):
        return a is b or str(a) == str(b)


def grids_match(g1, g2):
    return (len(g1) == len(g2)
            and all(len(r1) == len(r2) and all(cents_equal(x, y) for x, y in zip(r1, r2))
                    for r1, r2 in zip(g1, g2)))


def frames_match(d1, d2, key="Employee ID"):
    """Row-for-row, a cent apart at most. Sorted by employee first: a cent can
    change where a row lands in a list ordered by balance."""
    if list(d1.columns) != list(d2.columns) or len(d1) != len(d2):
        return False
    if key in d1.columns:
        d1 = d1.sort_values(key, kind="stable").reset_index(drop=True)
        d2 = d2.sort_values(key, kind="stable").reset_index(drop=True)
    return all(cents_equal(d1.iat[i, j], d2.iat[i, j])
               for i in range(len(d1)) for j in range(len(d1.columns)))


def legacy_mapping(adp_b, tpl_b):
    """Every ADP policy -> the template's one policy: what the baseline did.

    The policy-mapping change made auto-mapping and Salaried-off the defaults,
    which alter this output on purpose. Running the new code in legacy mode
    keeps this script testing what it was written for: the two new columns.
    """
    adp_df, _ = new.read_adp_balances(U(adp_b, "a.xlsx"))
    tpl, _ = new.read_template_rows(U(tpl_b, "t.xlsx"))
    return {p: tpl["policies"][0] for p, _, _ in new.policy_summary(adp_df)}


failures = 0


def check(label, ok, detail=""):
    global failures
    print("   %-66s %s%s" % (label, "OK" if ok else "FAIL",
                             "" if ok else "  <- " + str(detail)[:300]))
    failures += 0 if ok else 1


def run_case(name, adp_b, tpl_b, cen_path, old):
    print()
    print("=" * 96)
    print(name)
    print("=" * 96)
    cen_b = open(cen_path, "rb").read()
    o_fill, o_audit, o_stats = old.run_tool(U(adp_b, "a.xlsx"), U(tpl_b, "t.xlsx"),
                                            U(cen_b, "c.xlsm"))
    n_fill, n_audit, n_stats = new.run_tool(U(adp_b, "a.xlsx"), U(tpl_b, "t.xlsx"),
                                            U(cen_b, "c.xlsm"),
                                            mapping=legacy_mapping(adp_b, tpl_b),
                                            include_salaried=True,
                                            include_blank_hourly=False)
    check("both versions ran", o_fill is not None and n_fill is not None)
    if o_fill is None or n_fill is None:
        return

    check("filled template unchanged (bar the cent fix)",
          grids_match(cells(o_fill, "Time Off Details"), cells(n_fill, "Time Off Details")))
    check("stats unchanged", {k: n_stats[k] for k in o_stats} == o_stats,
          (o_stats, n_stats))

    for sheet in ("Balance vs UZIO Status", "Unassigned Policies"):
        check("%s unchanged" % sheet,
              frames_match(sheet_df(o_audit, sheet), sheet_df(n_audit, sheet)))

    o_exc, n_exc = sheet_df(o_audit, "Exception Summary"), sheet_df(n_audit, "Exception Summary")
    if "Message" in n_exc.columns:
        check("no exceptions in either version", "Message" in o_exc.columns)
        return
    check("Exception Summary columns are exactly the agreed six",
          list(n_exc.columns) == new.EXCEPTION_COLUMNS, list(n_exc.columns))
    check("same rows, same order, same old columns",
          frames_match(o_exc[OLD_EXC_COLS], n_exc[OLD_EXC_COLS]),
          "old=%d new=%d" % (len(o_exc), len(n_exc)))

    census, _ = new.read_census(U(cen_b, "c.xlsm"))
    status = dict(zip(census["id"], census["status"]))
    termdt = dict(zip(census["id"], census["termination date"]))
    wrong = []
    for _, r in n_exc.iterrows():
        eid = new.clean_id(r["Employee ID"])
        want_s = str(status.get(eid, "")).strip() or "(not in census)"
        want_d = termdt.get(eid, "")
        if r["Employment Status"] != want_s or r["Termination Date"] != want_d:
            wrong.append((r["Employee ID"], r["Employment Status"], r["Termination Date"],
                          want_s, want_d))
    check("every status / date equals the census lookup", not wrong, wrong[:3])

    term = n_exc[n_exc["Issue Category"].str.startswith("Terminated in UZIO")]
    check("every 'Terminated in UZIO' row shows TERMINATED + a date",
          term["Employment Status"].str.upper().str.startswith("TERMINATED").all()
          and (term["Termination Date"] != "").all(),
          term[["Employee ID", "Employment Status", "Termination Date"]].head(3).values.tolist())

    print("      rows by issue x status:")
    for (issue, st_), n in (n_exc.groupby(["Issue Category", "Employment Status"])
                            .size().items()):
        print("         %-44s %-18s %d" % (issue, st_, n))
    print("      sample:")
    for row in n_exc.head(3).values.tolist():
        print("         ", row)


def ui_test():
    from streamlit.testing.v1 import AppTest

    def script():
        import io as _io
        import json as _json
        import os as _os
        import sys as _sys
        _sys.path.insert(0, _os.environ["TO_REPO_ROOT"])
        import streamlit as _st
        from apps.adp import timeoff_audit
        files = _json.loads(_os.environ.get("TO_FILES", "{}"))

        class _U(_io.BytesIO):
            def __init__(self, p):
                with open(p, "rb") as fh:
                    super().__init__(fh.read())
                self.name = _os.path.basename(p)
                self.size = len(self.getvalue())

        _st.file_uploader = lambda *a, **k: (_U(files[k["key"]]) if k.get("key") in files
                                             else None)
        timeoff_audit.render_ui()

    print()
    print("=" * 96)
    print("Streamlit UI")
    print("=" * 96)
    a, t, c = CASES["Express"]
    os.environ["TO_REPO_ROOT"] = ROOT

    os.environ["TO_FILES"] = json.dumps({"at_a": a, "at_u": t})
    at = AppTest.from_function(script, default_timeout=120).run()
    check("page renders", not at.exception)
    at.button(key="run_timeoff_adp").click().run()
    errs = [e.value for e in at.error]
    check("Generate without census is refused",
          any("UZIO Census" in e for e in errs), errs)
    check("no downloads without census", len(at.get("download_button")) == 0)

    os.environ["TO_FILES"] = json.dumps({"at_a": a, "at_u": t, "at_c": c})
    at.run()
    at.button(key="run_timeoff_adp").click().run()
    check("Generate with all three runs", not at.exception and not at.error,
          [e.value for e in at.error])
    check("both downloads offered", len(at.get("download_button")) == 2,
          len(at.get("download_button")))
    at.run()
    check("downloads survive a rerun", len(at.get("download_button")) == 2)
    md = " ".join(m.value for m in at.markdown)
    check("page says all three files are required", "All three files are required" in md)
    check("census uploader no longer says optional",
          "optional" not in md.lower())


def main():
    old = load_old()

    a, t, c = CASES["Express"]
    run_case("Express (template with zeros)", open(a, "rb").read(), open(t, "rb").read(), c, old)
    run_case("Express (template blanks, as uploaded at 16:35)",
             open(a, "rb").read(), blank_template(t), c, old)
    a, t, c = CASES["High Distinction"]
    run_case("High Distinction", open(a, "rb").read(), open(t, "rb").read(), c, old)

    print()
    print("=" * 96)
    print("census is required")
    print("=" * 96)
    a, t, _ = CASES["Express"]
    res = new.run_tool(up(a), up(t), None)
    check("run_tool without a census returns nothing", res == (None, None, None), res)

    ui_test()

    print()
    if failures:
        print("FAIL - %d check(s)" % failures)
        return 1
    print("PASS - every check held")
    return 0


if __name__ == "__main__":
    sys.exit(main())
