"""Verify that pasted Employee IDs split on commas, new lines, semicolons and tabs.

Run:  python scratch/verify_id_paste_split.py [unit|extractor|report ...]

Before: the Selective Employee Extractor split on commas only, and the Employee
Profile Change Report meant to split on new lines too but replaced the literal
text "' + BS + 'n" instead of "\\n" - so an Excel column pasted into either
became ONE id. The old extractor is loaded from a PINNED commit (21d87a9).
"""
import json
import os
import subprocess
import sys
import tempfile

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from utils.id_input import split_ids          # noqa: E402

BASELINE = "21d87a9"
CENSUS = r"C:\Users\rohit.kaushik\Downloads\Banda Logistics\Multi_Client_Banda Logistics LLC_Employee_Census.xlsm"

failures = 0


def check(label, ok, detail=""):
    global failures
    print("   %-72s %s%s" % (label, "OK" if ok else "FAIL",
                             "" if ok else "  <- " + str(detail)[:300]))
    failures += 0 if ok else 1


# ---------------------------------------------------------------- unit
def group_unit():
    print("\n== split_ids")
    cases = [
        ("comma", "1020, BH0KS5HPZ, 8OSU7337G", ["1020", "BH0KS5HPZ", "8OSU7337G"]),
        ("Excel column (LF)", "1020\nBH0KS5HPZ\n8OSU7337G", ["1020", "BH0KS5HPZ", "8OSU7337G"]),
        ("Excel column (CRLF)", "1020\r\nBH0KS5HPZ\r\n8OSU7337G\r\n", ["1020", "BH0KS5HPZ", "8OSU7337G"]),
        ("Excel row (tabs)", "1020\tBH0KS5HPZ\t8OSU7337G", ["1020", "BH0KS5HPZ", "8OSU7337G"]),
        ("mixture", "1020, BH0KS5HPZ\n8OSU7337G;A03K\tA001", ["1020", "BH0KS5HPZ", "8OSU7337G", "A03K", "A001"]),
        ("stray separators", ",,\n 1020 ,\n\n, ;", ["1020"]),
        ("space INSIDE an id is kept", "123 456, 789", ["123 456", "789"]),
        ("hyphenated id is kept", "123-45-6789\n987", ["123-45-6789", "987"]),
        ("duplicates once, first order", "B, A, B\nA, C", ["B", "A", "C"]),
        ("leading zeros kept", "00123, 0456", ["00123", "0456"]),
        ("empty", "", []),
        ("None", None, []),
    ]
    for label, text, want in cases:
        got = split_ids(text)
        check("%-28s -> %s" % (label, want), got == want, got)

    for path in ("apps/common/employee_change_report.py", "apps/common/employee_extractor.py"):
        src = open(os.path.join(ROOT, path), encoding="utf-8").read()
        check("%s uses split_ids, no ' + BS + ' left" % path.split("/")[-1],
              "split_ids(" in src and "BS +" not in src)


# ---------------------------------------------------------------- extractor
def _extractor_script():
    import io as _io
    import json as _json
    import os as _os
    import sys as _sys
    import importlib.util as _ilu
    _sys.path.insert(0, _os.environ["IDS_ROOT"])
    import streamlit as _st
    path = _os.environ["IDS_MODULE"]
    spec = _ilu.spec_from_file_location("ee_under_test", path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    census = _os.environ["IDS_CENSUS"]

    class _U(_io.BytesIO):
        def __init__(self, p):
            with open(p, "rb") as fh:
                super().__init__(fh.read())
            self.name = _os.path.basename(p)
            self.size = len(self.getvalue())

    _st.file_uploader = lambda *a, **k: _U(census) if k.get("key") == "ee_source" else None
    mod.render_employee_extractor()


def _run_extractor(module_path, pasted):
    from streamlit.testing.v1 import AppTest
    os.environ.update({"IDS_ROOT": ROOT, "IDS_MODULE": module_path, "IDS_CENSUS": CENSUS})
    at = AppTest.from_function(_extractor_script, default_timeout=180).run()
    box = next(t for t in at.text_area if "Employee IDs" in t.label)
    box.set_value(pasted).run()
    matched = [s.value for s in at.success if s.value.startswith("Matched")]
    return at, matched


def group_extractor():
    print("\n== Selective Employee Extractor on the real Banda census")
    df = pd.read_excel(CENSUS, sheet_name="Employee Details", header=3, dtype=str)
    id_col = next(c for c in df.columns if "Employee ID" in str(c))
    ids = df[id_col].dropna().str.strip().tolist()[:3]
    print("   ids:", ids)
    old_src = subprocess.run(["git", "-C", ROOT, "show",
                              BASELINE + ":apps/common/employee_extractor.py"],
                             capture_output=True, text=True, encoding="utf-8", check=True).stdout
    old_path = os.path.join(tempfile.gettempdir(), "employee_extractor_baseline.py")
    open(old_path, "w", encoding="utf-8").write(old_src)
    new_path = os.path.join(ROOT, "apps", "common", "employee_extractor.py")

    pastes = {"comma": ", ".join(ids), "Excel column": "\n".join(ids),
              "mixture": ids[0] + ", " + ids[1] + "\n" + ids[2]}
    for label, text in pastes.items():
        _, old = _run_extractor(old_path, text)
        at, new = _run_extractor(new_path, text)
        check("%-13s before: %s" % (label, old[0] if old else "no match"),
              True)                                    # recorded, not asserted
        check("%-13s after : Matched 3" % label,
              new and "**3**" in new[0] and not at.exception, (new, [e.value for e in at.exception]))
    _, old = _run_extractor(old_path, "\n".join(ids))
    check("the old code really failed the Excel-column paste (proves the bug)",
          not old or "**3**" not in old[0], old)


# ---------------------------------------------------------------- report
def group_report():
    print("\n== Employee Profile Change Report form")
    from streamlit.testing.v1 import AppTest

    def script():
        import os as _os
        import sys as _sys
        _sys.path.insert(0, _os.environ["IDS_ROOT"])
        import streamlit as _st
        from apps.common import employee_change_report as m
        _st.session_state[m.TOKEN_KEY] = "test-token"      # skip the login screen
        _st.session_state[m.USER_KEY] = "tester"
        m.render_ui()

    os.environ["IDS_ROOT"] = ROOT
    at = AppTest.from_function(script, default_timeout=120).run()
    box = [t for t in at.text_area if "Employee IDs" in t.label]
    check("form renders without an exception", not at.exception and len(box) == 1,
          [e.value for e in at.exception])
    if box:
        check("placeholder shows a real line break, no ' + BS + '",
              box[0].placeholder == "1020, BH0KS5HPZ\n8OSU7337G", repr(box[0].placeholder))
        check("help text names new lines and mixtures", "new lines" in (box[0].help or ""))


GROUPS = {"unit": group_unit, "extractor": group_extractor, "report": group_report}


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
