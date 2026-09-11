"""Headless UI smoke test for the FIT/SIT Sanity tool.

Run:  python scratch/verify_fit_sit_ui.py

Drives the real Streamlit script through AppTest: upload a file, press Check
File, answer one dropdown, press build, and confirm both downloads appear. The
download buttons matter -- st.download_button triggers its own rerun, so results
have to live in session_state or the page falls back to the upload screen (the
bug the Time Off tool hit).

Also exercises the drift checker's "Java not on this machine" path.
"""
import io
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from streamlit.testing.v1 import AppTest        # noqa: E402

from apps.adp import fit_sit_sanity as fs       # noqa: E402

SAMPLE = os.path.join(ROOT, "scratch", "_fitsit_sample.csv")

ROWS = [
    # MO "Single" is rejected -> dropdown
    ("1001", "Ann", "Alpha", "MO", "Single", "", ""),
    ("1002", "Ben", "Bravo", "MO", "Single", "2", "No"),
    # WI punctuation-only -> auto-repaired
    ("1003", "Cat", "Charlie", "WI", "Married, but withhold at higher single rate", "", ""),
    # accepted as-is
    ("1004", "Dev", "Delta", "IA", "Single", "", ""),
    # state with no Uzio list
    ("1005", "Eve", "Echo", "PA", "Single", "", ""),
    # no state income tax
    ("1006", "Fay", "Foxtrot", "TX", "Single", "", ""),
    # no worked-in state at all
    ("1007", "Gil", "Golf", "", "", "", ""),
    # blank in a state that has a list -> dropdown
    ("1008", "Hal", "Hotel", "UT", "", "", ""),
]

COLUMNS = ["Associate ID", "Legal First Name", "Legal Last Name",
           "Worked in State Code", "State Marital Status Description",
           "Dependents", "Non-Resident Alien"]


def write_sample():
    pd.DataFrame(ROWS, columns=COLUMNS).to_csv(SAMPLE, index=False, encoding="utf-8")


class _Upload(io.BytesIO):
    def __init__(self, path):
        with open(path, "rb") as fh:
            super().__init__(fh.read())
        self.name = os.path.basename(path)
        self.size = len(self.getvalue())


def script():
    # AppTest re-executes this from source, so it gets no closure over ROOT --
    # everything comes in through the environment. AppTest also has no way to
    # drive st.file_uploader, so the uploader is stubbed to hand back the sample
    # file; every other widget is the real one.
    import io as _io
    import os as _os
    import sys as _sys

    _sys.path.insert(0, _os.environ["FITSIT_REPO_ROOT"])
    import streamlit as _st
    from apps.adp import fit_sit_sanity

    path = _os.environ.get("FITSIT_SAMPLE", "")
    if path:
        class _U(_io.BytesIO):
            def __init__(self, p):
                with open(p, "rb") as fh:
                    super().__init__(fh.read())
                self.name = _os.path.basename(p)
                self.size = len(self.getvalue())
        _st.file_uploader = lambda *a, **k: _U(path)
    else:
        _st.file_uploader = lambda *a, **k: None

    fit_sit_sanity.render_ui()


def ss(at, key):
    """AppTest's session_state has no .get()."""
    return at.session_state[key] if key in at.session_state else None


def dl_labels(at):
    """AppTest's download_button elements carry no key, so match on the label."""
    return [b.label for b in at.get("download_button")]


def check(label, condition, detail=""):
    print("   %-58s %s%s" % (label, "OK" if condition else "FAIL",
                             "" if condition else "  <- " + str(detail)))
    return 0 if condition else 1


def main():
    write_sample()
    os.environ["FITSIT_REPO_ROOT"] = ROOT
    os.environ["FITSIT_SAMPLE"] = ""
    failures = 0

    at = AppTest.from_function(script, default_timeout=60).run()
    failures += check("renders with no file", not at.exception,
                      at.exception[0].message if at.exception else "")
    failures += check("no buttons before a file", len(at.button) == 0)

    os.environ["FITSIT_SAMPLE"] = SAMPLE
    at.run()
    failures += check("renders with a file uploaded", not at.exception,
                      at.exception[0].message if at.exception else "")

    at.button(key="adp_fitsit_run").click().run()
    failures += check("Check File runs", not at.exception,
                      at.exception[0].message if at.exception else "")

    plan = ss(at, "adp_fitsit_plan")
    failures += check("plan is stored in session_state", plan is not None)
    failures += check("two dropdowns offered", plan and len(plan["decisions"]) == 2,
                      plan and plan["decisions"])
    failures += check("selectboxes rendered", len(at.selectbox) == 2, len(at.selectbox))

    # Answer only the MO one; leave UT alone on purpose.
    mo = next(s for s in at.selectbox if "MO" in s.label)
    ut = next(s for s in at.selectbox if "UT" in s.label)
    failures += check("nothing pre-selected",
                      mo.value == fs.LEAVE_AS_IS and ut.value == fs.LEAVE_AS_IS,
                      (mo.value, ut.value))
    mo.select("SINGLE OR MARRIED SPOUSE WORKS OR MARRIED FILING SEPARATE").run()

    at.button(key="adp_fitsit_build").click().run()
    failures += check("build runs", not at.exception,
                      at.exception[0].message if at.exception else "")

    out = ss(at, "adp_fitsit_out")
    failures += check("results in session_state", out is not None)
    xlsx_dl = [l for l in dl_labels(at) if l.endswith("(.xlsx)")]
    csv_dl = [l for l in dl_labels(at) if l.endswith("(.csv)")]
    failures += check("both downloads offered",
                      len(xlsx_dl) == 1 and len(csv_dl) == 1, dl_labels(at))

    # st.download_button triggers its own rerun; the results must survive it.
    at.run()
    failures += check("results survive a rerun",
                      ss(at, "adp_fitsit_out") is not None
                      and len(dl_labels(at)) == 2,
                      dl_labels(at))

    _, csv_bytes, summary, changes, review = at.session_state["adp_fitsit_out"]
    got = pd.read_csv(io.BytesIO(csv_bytes), dtype=str).fillna("")
    col = "State Marital Status Description"
    failures += check("MO rows written from the mapping",
                      set(got.loc[[0, 1], col]) ==
                      {"SINGLE OR MARRIED SPOUSE WORKS OR MARRIED FILING SEPARATE"},
                      list(got.loc[[0, 1], col]))
    failures += check("WI punctuation repaired",
                      got.at[2, col] == "MARRIED BUT WITHHOLD AT HIGHER SINGLE RATE",
                      got.at[2, col])
    failures += check("accepted value untouched", got.at[3, col] == "Single")
    failures += check("state with no list untouched", got.at[4, col] == "Single")
    failures += check("no-SIT state untouched", got.at[5, col] == "Single")
    failures += check("row with no state left blank", got.at[6, col] == "")
    failures += check("unmapped UT blank left blank", got.at[7, col] == "")
    failures += check("Dependents still filled",
                      list(got["Dependents"]) == ["0", "2", "0", "0", "0", "0", "0", "0"],
                      list(got["Dependents"]))
    failures += check("Non-Resident Alien still filled",
                      set(got["Non-Resident Alien"]) == {"No"},
                      list(got["Non-Resident Alien"]))
    failures += check("review sheet shows the skipped UT pair",
                      ((review["State"] == "UT") &
                       (review["Result"].str.startswith("Still rejected"))).any(),
                      review.to_dict("records"))
    failures += check("review sheet lists the stateless row",
                      (review["Result"].str.startswith("No worked-in state")).any())
    failures += check("change log carries old value and reason",
                      set(changes.columns) >= {"Old Value", "Reason", "State"})

    # --- the checker's no-Java path
    print()
    import utils.check_state_filing_status as chk
    saved = chk.CANDIDATE_ROOTS
    chk.CANDIDATE_ROOTS = [r"Z:\nope"]
    rc = chk.main()
    chk.CANDIDATE_ROOTS = saved
    failures += check("checker exits 0 when the Java is absent", rc == 0, rc)

    os.remove(SAMPLE)
    print()
    if failures:
        print("FAIL - %d check(s)" % failures)
        return 1
    print("PASS - every UI check held")
    return 0


if __name__ == "__main__":
    sys.exit(main())
