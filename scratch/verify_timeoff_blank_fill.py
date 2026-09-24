"""Verify the Hourly blank-fill checkbox and the "nothing was written" message.

Run:  python scratch/verify_timeoff_blank_fill.py [off|moses|hd|express|unit|ui ...]

Spec: docs/superpowers/specs/2026-09-25-adp-timeoff-blank-fill-design.md

A blank Opening Balance means "policy not assigned" in UZIO, so filling one
ASSIGNS the policy. With the checkbox off (the default) nothing may change.
"""
import importlib.util
import io
import os
import subprocess
import sys
import tempfile

import openpyxl
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from apps.adp import timeoff_audit as ta          # noqa: E402

BASELINE = "34a457f"          # main before this change
D = r"C:\Users\rohit.kaushik\Downloads"
MOSES = (D + r"\Moses_Solutions_LLC_Time_Off_Balance_Summary.xlsx",
         D + r"\Moses_Time Off Import (2).xlsx", None)
EXPRESS = (D + r"\Express_Package_System_Inc_Time_Off_Balance_Summary.xlsx",
           D + r"\Time Off Import (1).xlsx",
           D + r"\Multi_Client_EXPRESS PACKAGE SYSTEM_Employee_Census.xlsm")
HD = (D + r"\High Distinction\New folder\Time Off Balance Summary.xlsx",
      D + r"\High Distinction\New folder\Time Off Import.xlsx",
      D + r"\High Distinction\Multi_Client_High Distinction Logistics LLC_Employee_Census.xlsm")

failures = 0


class U(io.BytesIO):
    def __init__(self, data, name):
        super().__init__(data)
        self.name = name
        self.size = len(data)


def up(path):
    return U(open(path, "rb").read(), os.path.basename(path))


def check(label, ok, detail=""):
    global failures
    print("   %-68s %s%s" % (label, "OK" if ok else "FAIL",
                             "" if ok else "  <- " + str(detail)[:300]))
    failures += 0 if ok else 1


def baseline():
    src = subprocess.run(["git", "-C", ROOT, "show", BASELINE + ":apps/adp/timeoff_audit.py"],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    path = os.path.join(tempfile.gettempdir(), "timeoff_blankfill_baseline.py")
    open(path, "w", encoding="utf-8").write(src)
    spec = importlib.util.spec_from_file_location("timeoff_blankfill_baseline", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parts(mod, files, include_salaried=False, include_blank_hourly=None):
    """Read + plan + fill without Streamlit, so Moses (no census) works too."""
    a, t, _ = files
    adp_df, err = mod.read_adp_balances(up(a))
    assert not err, err
    tpl, err = mod.read_template_rows(up(t))
    assert not err, err
    auto = mod.auto_map([p for p, _, _ in mod.policy_summary(adp_df)], tpl["policies"])
    if include_blank_hourly is None:
        plan = mod.plan_fill(tpl, adp_df, auto, include_salaried)
    else:
        plan = mod.plan_fill(tpl, adp_df, auto, include_salaried, include_blank_hourly)
    wb, filled, err = mod.fill_import_template(up(t), plan["decisions"])
    assert not err, err
    sheets, counts = mod.build_audit_sheets(up(t), tpl, adp_df, None, plan, auto, auto)
    return {"adp": adp_df, "tpl": tpl, "auto": auto, "plan": plan, "wb": wb,
            "filled": filled, "sheets": sheets, "counts": counts}


def openings(wb):
    ws = ta._template_sheet(wb)
    return {r: ws.cell(row=r, column=8).value
            for r in range(ta.UZIO_HEADER_ROW + 1, ws.max_row + 1)}


def cents_equal(a, b, tol=0.011):
    """Equal, or a cent apart.

    The baseline rounds every ADP transaction before adding; the working tree
    adds first and rounds once, the way ADP's own subtotal does. That moves
    some balances by 0.01, which is the point of that fix, not a regression.
    """
    if a is None and b is None:
        return True
    try:
        fa, fb = float(a), float(b)
        if fa != fa and fb != fb:          # both NaN
            return True
        return abs(fa - fb) <= tol
    except (TypeError, ValueError):
        return a is b or str(a) == str(b)


def same_openings(a, b):
    return set(a) == set(b) and all(cents_equal(a[k], b[k]) for k in a)


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


def policy_mapping_match(d1, d2):
    """Same, but a policy's Total is a sum over everyone on it, so the per-row
    cent fix can move it by up to a cent per employee."""
    if list(d1.columns) != list(d2.columns) or len(d1) != len(d2):
        return False
    for i in range(len(d1)):
        for c in d1.columns:
            a, b = d1.iloc[i][c], d2.iloc[i][c]
            if c == "Total ADP Balance":
                try:                      # numpy ints are not Python ints
                    n = float(d1.iloc[i]["Employees"])
                except (TypeError, ValueError):
                    n = 1.0
                if not cents_equal(a, b, 0.011 * max(1.0, n)):
                    return False
            elif not cents_equal(a, b):
                return False
    return True


def blank_template_bytes(path):
    wb = openpyxl.load_workbook(path)
    ws = ta._template_sheet(wb)
    for r in range(ta.UZIO_HEADER_ROW + 1, ws.max_row + 1):
        if ws.cell(row=r, column=3).value not in (None, ""):
            ws.cell(row=r, column=8).value = None
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- off
def group_off():
    print("\n== checkbox off: nothing may change")
    base = baseline()
    for name, files in (("Moses", MOSES), ("Express", EXPRESS), ("High Distinction", HD)):
        old, new = parts(base, files), parts(ta, files, include_blank_hourly=False)
        check("%s: filled template identical (bar the cent fix)" % name,
              same_openings(openings(old["wb"]), openings(new["wb"])))
        check("%s: rows written identical (%d)" % (name, old["filled"]),
              old["filled"] == new["filled"], (old["filled"], new["filled"]))
        for s in old["sheets"]:
            same = (policy_mapping_match if s == "Policy Mapping" else frames_match)
            check("%s: %s sheet identical (bar the cent fix)" % (name, s),
                  same(old["sheets"][s], new["sheets"][s]))


# ---------------------------------------------------------------- clients
def _blank_case(name, files, expected):
    print("\n== %s: checkbox on" % name)
    off = parts(ta, files, include_blank_hourly=False)
    on = parts(ta, files, include_blank_hourly=True)
    o_open, n_open = openings(off["wb"]), openings(on["wb"])
    changed = {r: n_open[r] for r in o_open if o_open[r] != n_open[r]}
    by_id = {t["row"]: t for t in on["tpl"]["rows"]}
    got = {str(by_id[r]["raw_id"]): v for r, v in changed.items()}
    check("only the expected rows changed", got == expected, got)
    check("rows written = off + %d" % len(expected),
          on["filled"] == off["filled"] + len(expected), (off["filled"], on["filled"]))
    check("every Salaried blank row is untouched",
          all(n_open[t["row"]] == t["opening"] for t in on["tpl"]["rows"]
              if t["salaried"] and ta._is_blank(t["opening"])))

    exc = on["sheets"]["Exception Summary"]
    filled_rows = exc[exc["Issue Category"].str.startswith("Blank filled")]
    check("each filled row is reported with its amount",
          {str(r["Employee ID"]): float(r["ADP Balance"]) for _, r in filled_rows.iterrows()}
          == {k: float(v) for k, v in expected.items()},
          filled_rows[["Employee ID", "Issue Category", "ADP Balance"]].values.tolist())
    check("the category names the policy",
          all("(" in c and c.rstrip().endswith(")") for c in filled_rows["Issue Category"]),
          list(filled_rows["Issue Category"]))

    un_off = off["sheets"]["Unassigned Policies"]
    un_on = on["sheets"]["Unassigned Policies"]
    check("Unassigned Policies drops exactly the filled rows",
          len(un_on) == len(un_off) - len(expected), (len(un_off), len(un_on)))
    still = exc[exc["Issue Category"] == "Unassigned Policy (Blank Balance)"]
    check("no row is both filled and unassigned",
          not (set(filled_rows["Employee ID"]) & set(still["Employee ID"])))
    check("counts carry the filled total", on["counts"].get("blank_filled") == len(expected),
          on["counts"].get("blank_filled"))


def group_moses():
    # 113.36, not .37: ADP's own subtotal for Gadiel Soto.
    _blank_case("Moses", MOSES, {"AGMOSZNLA": 20.65, "K0R9USFW5": 113.36})


def group_hd():
    _blank_case("High Distinction", HD,
                {"VNO9RTFG4": 1.77, "XL50T0H6Y": 1.7, "WQ0EJMZ91": 6.95})


def group_express():
    print("\n== Express: no blank rows, so the checkbox changes nothing")
    off = parts(ta, EXPRESS, include_blank_hourly=False)
    on = parts(ta, EXPRESS, include_blank_hourly=True)
    check("filled template identical", openings(off["wb"]) == openings(on["wb"]))
    check("rows written identical", off["filled"] == on["filled"])


# ---------------------------------------------------------------- unit
def group_unit():
    print("\n== a 0.00 balance still assigns the policy")
    tpl = {"sheet": "Time Off Details", "policies": ["Paid PTO"], "has_pay_type": True,
           "rows": [
               {"row": 5, "raw_id": "H1", "id": "H1", "name": "Hourly Zero",
                "policy": "Paid PTO", "opening": None, "salaried": False},
               {"row": 6, "raw_id": "S1", "id": "S1", "name": "Salaried Zero",
                "policy": "Paid PTO", "opening": None, "salaried": True},
               {"row": 7, "raw_id": "H2", "id": "H2", "name": "Hourly No ADP",
                "policy": "Paid PTO", "opening": None, "salaried": False},
           ]}
    adp = pd.DataFrame([{"id": "H1", "policy": "PTO", "balance": 0.0, "name": "Hourly Zero"},
                        {"id": "S1", "policy": "PTO", "balance": 8.0, "name": "Salaried Zero"}])
    mapping = {"PTO": "Paid PTO"}
    plan = ta.plan_fill(tpl, adp, mapping, False, True)
    acts = {t["raw_id"]: (a, amt) for t, a, amt in plan["decisions"]}
    check("an Hourly blank with a 0.00 balance is written",
          acts["H1"] == ("write_blank", 0.0), acts["H1"])
    check("a Salaried blank is left alone even with the box on",
          acts["S1"][0] == "blank", acts["S1"])
    check("an Hourly blank with no ADP balance stays blank",
          acts["H2"][0] == "blank", acts["H2"])
    plan = ta.plan_fill(tpl, adp, mapping, True, True)
    acts = {t["raw_id"]: a for t, a, _ in plan["decisions"]}
    check("the Salaried checkbox does not unlock Salaried blanks",
          acts["S1"] == "blank", acts["S1"])


# ---------------------------------------------------------------- ui
def group_ui():
    print("\n== the screen")
    import json
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

    a, t, c = EXPRESS
    os.environ["TO_REPO_ROOT"] = ROOT

    os.environ["TO_FILES"] = json.dumps({"at_a": a, "at_u": t, "at_c": c})
    at = AppTest.from_function(script, default_timeout=180).run()
    labels = [cb.label for cb in at.checkbox]
    check("a second checkbox appears, for blank Hourly rows",
          len(at.checkbox) == 2 and any("blank" in l.lower() for l in labels), labels)
    blank_cb = [cb for cb in at.checkbox if "blank" in cb.label.lower()]
    sal_cb = [cb for cb in at.checkbox if "salaried" in cb.label.lower()]
    check("the blank-row box starts CHECKED, the Salaried one unchecked",
          len(blank_cb) == 1 and blank_cb[0].value is True
          and len(sal_cb) == 1 and sal_cb[0].value is False,
          [(cb.label, cb.value) for cb in at.checkbox])
    at.button(key="run_timeoff_adp").click().run()
    check("a normal run still shows the green message",
          len(at.success) == 1 and not at.error,
          ([s.value for s in at.success], [e.value for e in at.error]))

    # every Opening Balance blank: on by default those rows get filled
    blank = os.path.join(tempfile.gettempdir(), "express_all_blank.xlsx")
    open(blank, "wb").write(blank_template_bytes(t))
    os.environ["TO_FILES"] = json.dumps({"at_a": a, "at_u": blank, "at_c": c})
    at = AppTest.from_function(script, default_timeout=180).run()
    at.button(key="run_timeoff_adp").click().run()
    check("an all-blank template is filled with the box on by default",
          len(at.success) == 1 and not at.error, [e.value for e in at.error])
    check("and the screen says how many blank rows were filled",
          any("blank row" in i.value for i in at.info), [i.value for i in at.info])

    # same file with the box off -> nothing can be written
    at = AppTest.from_function(script, default_timeout=180).run()
    next(cb for cb in at.checkbox if "blank" in cb.label.lower()).set_value(False).run()
    at.button(key="run_timeoff_adp").click().run()
    msgs = [e.value for e in at.error]
    check("a run that writes nothing shows a red message", len(msgs) == 1, msgs)
    check("and no green one", not at.success, [s.value for s in at.success])
    check("the red message says why", msgs and "200" in msgs[0], msgs)
    check("both downloads are still offered", len(at.get("download_button")) == 2)


GROUPS = {"off": group_off, "moses": group_moses, "hd": group_hd,
          "express": group_express, "unit": group_unit, "ui": group_ui}


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
