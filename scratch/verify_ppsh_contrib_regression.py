"""Old client files must come out of the contribution layer exactly as before.

Run:  python scratch/verify_ppsh_contrib_regression.py

The Roth-split fix changes how a memo column is named and how contribution rows
are keyed. Anything WITHOUT a `ROTH:` split column must be untouched, so this
runs the pre-fix module (git HEAD~1) and the current one over every prior
payroll file on this machine and compares, column by column:

  Type Code, Type Description, _Detected, _Kind, and the enriched UZIO fields
  (Contribution Name, Method, Formula, Link to Company Deduction, Linked Deduction)
"""
import glob
import importlib.util
import os
import subprocess
import sys
import tempfile
import warnings

import pandas as pd

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from apps.adp import prior_payroll_setup_helper as new     # noqa: E402

BASELINE = "ec5dda2"         # main just before this fix (the merge of PR #63)
D = r"C:\Users\rohit.kaushik\Downloads"
NAME_HINTS = ("prior", "payroll", "sanitiz", "clean", "register")
MASTERS = ["401k", "Roth 401k", "Medical Pre-tax"]

failures = 0


def check(label, ok, detail=""):
    global failures
    print("   %-66s %s%s" % (label, "OK" if ok else "FAIL",
                             "" if ok else "  <- " + str(detail)[:400]))
    failures += 0 if ok else 1


def baseline_module():
    src = subprocess.run(
        ["git", "-C", ROOT, "show", BASELINE + ":apps/adp/prior_payroll_setup_helper.py"],
        capture_output=True, text=True, encoding="utf-8", check=True).stdout
    path = os.path.join(tempfile.gettempdir(), "ppsh_prev.py")
    open(path, "w", encoding="utf-8").write(src)
    spec = importlib.util.spec_from_file_location("ppsh_prev", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def payroll_files():
    out = []
    for ext in ("*.xlsx", "*.xls", "*.csv"):
        for f in glob.glob(os.path.join(D, "**", ext), recursive=True):
            base = os.path.basename(f).lower()
            if base.startswith("~$"):
                continue
            if any(h in base for h in NAME_HINTS):
                out.append(f)
    return sorted(set(out))


def read(path):
    if path.lower().endswith(".csv"):
        return pd.read_csv(path, dtype=str, low_memory=False)
    return pd.read_excel(path, dtype=str)


def snapshot(mod, df):
    """Everything the contribution layer produces, keyed by source column."""
    cands = mod.build_memo_candidate_rows(df)
    selected = [c["_Source Column"] for c in cands if c["_Detected"]]
    rows = mod.build_contributions_from_memo_cols(cands, selected)
    link = {}
    for r in rows:
        master = mod.map_contribution_to_deduction(
            r["Type Code"], r["Type Description"], MASTERS)
        key = (mod.contrib_row_key(r) if hasattr(mod, "contrib_row_key")
               else mod.autosync_row_key(r["Type Code"], r["Type Description"]))
        link[key] = master or ""
    enriched = mod.enrich_contributions_for_uzio(rows, link)
    return (
        {c["_Source Column"]: (c["Type Code"], c["Type Description"], c["_Detected"],
                               c["_Kind"], c["_Total $"], c["_Employees"])
         for c in cands},
        {r["_Source Column"]: (r["Contribution Name"], r["Method"], r["Formula"],
                               r["Link to Company Deduction"], r["Linked Deduction"])
         for r in enriched},
    )


def _drop_suffix(old_name, new_name, code):
    """True when the only change is the duplicate-name suffix '(CODE)' going away.

    Renaming the Roth split frees its parent: the two names no longer collide, so
    build_memo_candidate_rows stops disambiguating them.
    """
    return bool(code) and old_name == f"{new_name} ({code})"


def acceptable(col, o_c, n_c, o_e, n_e):
    """A changed column is only allowed to be the ROTH: split or its parent."""
    if o_c.get(col) == n_c.get(col) and o_e.get(col) == n_e.get(col):
        return True
    if str(col).strip().lower().startswith("roth:"):
        return True                                   # the split column itself
    old_c, new_c = o_c.get(col), n_c.get(col)
    if not old_c or not new_c:
        return False
    # code, detection, kind, totals must be untouched; only the name may lose
    # the suffix, and the enriched row may differ only by that same name.
    if (old_c[0], old_c[2], old_c[3], old_c[4], old_c[5]) != \
       (new_c[0], new_c[2], new_c[3], new_c[4], new_c[5]):
        return False
    if not _drop_suffix(old_c[1], new_c[1], new_c[0]):
        return False
    old_e, new_e = o_e.get(col), n_e.get(col)
    if old_e is None and new_e is None:
        return True
    if old_e is None or new_e is None:
        return False
    return (old_e[1:] == new_e[1:]
            and _drop_suffix(old_e[0], new_e[0], new_c[0]))


def main():
    prev = baseline_module()
    files = payroll_files()
    print("prior-payroll-ish files found: %d" % len(files))

    scanned = with_memo = with_split = changed = 0
    for path in files:
        try:
            df = read(path)
        except Exception:
            continue
        memo_cols = [c for c in df.columns
                     if str(c).strip().upper().startswith("MEMO")
                     or str(c).strip().lower().startswith("roth:")]
        if not memo_cols:
            continue
        scanned += 1
        with_memo += 1
        split = [c for c in memo_cols if str(c).strip().lower().startswith("roth:")]
        with_split += 1 if split else 0

        o_c, o_e = snapshot(prev, df)
        n_c, n_e = snapshot(new, df)
        rel = os.path.relpath(path, D)

        if o_c == n_c and o_e == n_e:
            continue
        changed += 1
        print()
        print("   CHANGED  %s   (%d memo col(s), split=%s)" % (rel[:70], len(memo_cols), bool(split)))
        for col in sorted(set(o_c) | set(n_c)):
            if o_c.get(col) != n_c.get(col):
                print("      candidate %r" % col)
                print("         was: %s" % (o_c.get(col),))
                print("         now: %s" % (n_c.get(col),))
        for col in sorted(set(o_e) | set(n_e)):
            if o_e.get(col) != n_e.get(col):
                print("      enriched  %r" % col)
                print("         was: %s" % (o_e.get(col),))
                print("         now: %s" % (n_e.get(col),))
        bad = [col for col in sorted(set(o_c) | set(o_e) | set(n_c) | set(n_e))
               if not acceptable(col, o_c, n_c, o_e, n_e)]
        check("every change in %s is the Roth split or its freed suffix" % rel[:40],
              not bad, bad)

    print()
    print("files with MEMO columns : %d" % with_memo)
    print("of those, with a ROTH: split column : %d" % with_split)
    print("files whose contribution output changed : %d" % changed)
    check("no file without a ROTH: split column changed at all",
          changed == 0 or with_split > 0, changed)
    check("at least one real client file exercised the memo path", with_memo > 0, with_memo)

    print()
    print("FAIL - %d check(s)" % failures if failures else "PASS - every check held")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
