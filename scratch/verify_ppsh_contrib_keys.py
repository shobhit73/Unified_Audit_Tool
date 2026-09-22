"""Verify the contribution linker survives the Sanity check's ROTH: split column.

Run:  python scratch/verify_ppsh_contrib_keys.py

`prior_payroll_sanity.split_memo_column` splits a combined employer-match memo
into `MEMO : X` plus `ROTH:MEMO : X`, keeping both. With a descriptive label
("K-401K MATCH") the setup helper gave BOTH columns the same Type Code and the
same Type Description, so:

  * st.selectbox was called twice with key adp_ppsh_contriblink::K||401K Match (K)
    -> StreamlitDuplicateElementKey, the whole tool dead
  * the Roth half was named "401K Match" and auto-linked to the 401k deduction
    instead of Roth 401k
"""
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from apps.adp import prior_payroll_setup_helper as h    # noqa: E402

DEDS = [
    {"UZIO Master Deductions List": "401k", "UZIO Deduction Name": "401k EE"},
    {"UZIO Master Deductions List": "Roth 401k", "UZIO Deduction Name": "Roth 401k EE"},
]

failures = 0


def check(label, ok, detail=""):
    global failures
    print("   %-64s %s%s" % (label, "OK" if ok else "FAIL",
                             "" if ok else "  <- " + str(detail)[:300]))
    failures += 0 if ok else 1


def frame(memo_cols):
    # Three rows: the value-based detector needs n >= 3 before it will look.
    data = {"GROSS PAY": [1000.0, 2000.0, 1500.0],
            "VOLUNTARY DEDUCTION : 401K": [50.0, 100.0, 75.0]}
    for c in memo_cols:
        data[c] = [30.0, 60.0, 45.0]
    return pd.DataFrame(data)


def candidates(memo_cols):
    return h.build_memo_candidate_rows(frame(memo_cols))


# The shapes the sanity split can produce: it writes an UPPERCASE ROTH: prefix,
# and the label may be descriptive or an opaque letter code.
SPLIT_SHAPES = {
    "descriptive label": ["MEMO : K-401K MATCH", "ROTH:MEMO : K-401K MATCH"],
    "no code in label": ["MEMO : 401K MATCH", "ROTH:MEMO : 401K MATCH"],
    "opaque label": ["MEMO : N", "ROTH:MEMO : N"],
    "lowercase prefix": ["MEMO : K-401K MATCH", "Roth:MEMO : K-401K MATCH"],
}


def group_keys():
    print("\n== keys and names")
    for name, cols in SPLIT_SHAPES.items():
        cands = candidates(cols)
        keys = [h.contrib_row_key(c) for c in cands]
        names = [c["Type Description"] for c in cands]
        check("%s: one widget key per memo column" % name,
              len(set(keys)) == len(cands) == 2, (keys, names))
        roth = next((c for c in cands
                     if str(c["_Source Column"]).lower().startswith("roth:")), None)
        check("%s: the Roth column is named Roth" % name,
              roth is not None and "roth" in str(roth["Type Description"]).lower(),
              names)
        check("%s: the two contributions have different names" % name,
              len(set(names)) == 2, names)


def group_linking():
    print("\n== default linking")
    cands = candidates(SPLIT_SHAPES["descriptive label"])
    masters = [d["UZIO Master Deductions List"] for d in DEDS]
    got = {c["_Source Column"]: h.map_contribution_to_deduction(
        c["Type Code"], c["Type Description"], masters) for c in cands}
    check("the Roth half defaults to Roth 401k, the other to 401k",
          got == {"MEMO : K-401K MATCH": "401k", "ROTH:MEMO : K-401K MATCH": "Roth 401k"},
          got)

    link_map = {h.contrib_row_key(c): ("Roth 401k EE" if c["_Kind"] == "roth" else "401k EE")
                for c in cands}
    enriched = h.enrich_contributions_for_uzio(cands, link_map)
    got = {r["_Source Column"]: r["Linked Deduction"] for r in enriched}
    check("each row keeps its own linked deduction",
          got == {"MEMO : K-401K MATCH": "401k EE",
                  "ROTH:MEMO : K-401K MATCH": "Roth 401k EE"}, got)


def group_unchanged():
    print("\n== unchanged for files without a split")
    cands = candidates(["MEMO : K-401K MATCH"])
    check("a lone descriptive memo keeps its name",
          [c["Type Description"] for c in cands] == ["401K Match"],
          [c["Type Description"] for c in cands])
    cands = candidates(["MEMO : N", "MEMO : P"])
    check("opaque memo columns still get the code suffix",
          sorted(c["Type Description"] for c in cands)
          == ["401K Match (N)", "401K Match (P)"],
          [c["Type Description"] for c in cands])
    check("every candidate still has a distinct key",
          len({h.contrib_row_key(c) for c in cands}) == 2)


def group_ui():
    print("\n== the real Streamlit section")
    from streamlit.testing.v1 import AppTest

    def script():
        import os as _os
        import sys as _sys
        _sys.path.insert(0, _os.environ["PPSH_REPO_ROOT"])
        import pandas as _pd
        from apps.adp import prior_payroll_setup_helper as _h

        cols = _os.environ["PPSH_COLS"].split("|")
        data = {"GROSS PAY": [1000.0, 2000.0, 1500.0],
                "VOLUNTARY DEDUCTION : 401K": [50.0, 100.0, 75.0]}
        for c in cols:
            data[c] = [30.0, 60.0, 45.0]
        cands = _h.build_memo_candidate_rows(_pd.DataFrame(data))
        _h._render_contribution_setup_section(
            {"Memo_Candidates": cands},
            [{"UZIO Master Deductions List": "401k", "UZIO Deduction Name": "401k EE"},
             {"UZIO Master Deductions List": "Roth 401k",
              "UZIO Deduction Name": "Roth 401k EE"}])

    os.environ["PPSH_REPO_ROOT"] = ROOT
    for name, cols in SPLIT_SHAPES.items():
        os.environ["PPSH_COLS"] = "|".join(cols)
        at = AppTest.from_function(script, default_timeout=120).run()
        err = at.exception[0].message if at.exception else ""
        check("%s: section renders without a duplicate-key error" % name,
              not at.exception, err)
        if at.exception:
            continue
        # Auto-detection may pick only one of the pair (an opaque label needs the
        # value test, which wants more rows). Select both by hand so the linker
        # renders a widget for each — the path that used to raise.
        at.multiselect[0].set_value(cols).run()
        err = at.exception[0].message if at.exception else ""
        check("%s: both columns selected -> two link dropdowns" % name,
              not at.exception and len(at.selectbox) == 2, err or len(at.selectbox))


def group_baseline():
    """The committed code must still reproduce the error the client hit."""
    print("\n== the bug, on the pre-fix code")
    import subprocess
    import tempfile
    from streamlit.testing.v1 import AppTest

    src = subprocess.run(
        ["git", "-C", ROOT, "show", "HEAD:apps/adp/prior_payroll_setup_helper.py"],
        capture_output=True, text=True, encoding="utf-8", check=True).stdout
    path = os.path.join(tempfile.gettempdir(), "ppsh_baseline.py")
    open(path, "w", encoding="utf-8").write(src)
    os.environ["PPSH_BASELINE"] = path
    os.environ["PPSH_COLS"] = "|".join(SPLIT_SHAPES["descriptive label"])

    def script():
        import importlib.util as _il
        import os as _os
        import sys as _sys
        _sys.path.insert(0, _os.environ["PPSH_REPO_ROOT"])
        import pandas as _pd
        spec = _il.spec_from_file_location("ppsh_baseline", _os.environ["PPSH_BASELINE"])
        _h = _il.module_from_spec(spec)
        spec.loader.exec_module(_h)

        cols = _os.environ["PPSH_COLS"].split("|")
        data = {"GROSS PAY": [1000.0, 2000.0, 1500.0],
                "VOLUNTARY DEDUCTION : 401K": [50.0, 100.0, 75.0]}
        for c in cols:
            data[c] = [30.0, 60.0, 45.0]
        cands = _h.build_memo_candidate_rows(_pd.DataFrame(data))
        _h._render_contribution_setup_section(
            {"Memo_Candidates": cands},
            [{"UZIO Master Deductions List": "401k", "UZIO Deduction Name": "401k EE"},
             {"UZIO Master Deductions List": "Roth 401k",
              "UZIO Deduction Name": "Roth 401k EE"}])

    at = AppTest.from_function(script, default_timeout=120).run()
    # Streamlit's wording: "There are multiple elements with the same `key=...`".
    msg = "".join(str(e.message) + str(e.value) for e in at.exception)
    check("pre-fix code raises the duplicate-key error the client reported",
          "multiple elements with the same" in msg and "adp_ppsh_contriblink::" in msg,
          msg[:200] or "no exception")


def main():
    group_keys()
    group_linking()
    group_unchanged()
    group_ui()
    group_baseline()
    print()
    print("FAIL - %d check(s)" % failures if failures else "PASS - every check held")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
