"""Verify the FIT/SIT filing-status change against every client file on this machine.

Run:  python scratch/verify_fit_sit_filing_status.py

Checks, in order:
  1. classification totals across every FIT/SIT export found on disk
  2. that the "accepted" bucket really is accepted -- reproduce the API's own
     `toUpperCase().trim()` lookup and confirm every such row resolves to an enum
  3. that a punctuation repair always lands on an accepted label
  4. regression: with no mappings chosen, the corrected file must differ from the
     pre-change tool's output ONLY by no longer writing a blind "Single"
  5. with mappings supplied, that every mapped row is written and nothing else moves
"""
import glob
import io
import os
import sys
from collections import Counter

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from apps.adp import fit_sit_sanity as fs           # noqa: E402
from utils import state_filing_status as sfs        # noqa: E402

SEARCH_DIR = r"C:\Users\rohit.kaushik\Downloads"
KEYS = ("sit fit", "fit_sit", "fit sit")
STATUS = "State Marital Status Description"
STATE = "Worked in State Code"


class _Upload(io.BytesIO):
    """Minimal stand-in for a Streamlit UploadedFile."""

    def __init__(self, path):
        with open(path, "rb") as fh:
            super().__init__(fh.read())
        self.name = os.path.basename(path)


def find_files():
    out = []
    for path in glob.glob(os.path.join(SEARCH_DIR, "**", "*.csv"), recursive=True):
        if any(k in os.path.basename(path).lower() for k in KEYS):
            out.append(path)
    return sorted(out)


def old_tool_output(df):
    """What the pre-change tool wrote: every blank filled with a fixed default."""
    old = df.copy()
    for col, default in (("Dependents", "0"),
                         ("Non-Resident Alien", "No"),
                         (STATUS, "Single")):
        if col in old.columns:
            blank = old[col].isna() | (old[col].astype(str).str.strip() == "")
            old.loc[blank, col] = default
    return old


def main():
    files = find_files()
    if not files:
        print("no FIT/SIT files found under", SEARCH_DIR)
        return 1

    totals = Counter()
    all_pairs = Counter()
    failures = 0
    worst = (0, "")

    print("=" * 96)
    print("classification per file")
    print("=" * 96)

    for path in files:
        try:
            df = pd.read_csv(path, dtype=str)
        except UnicodeDecodeError:
            # Pre-existing: the tool itself would also fail on this file.
            df = pd.read_csv(path, dtype=str, encoding="cp1252")
            totals["cp1252 files"] += 1
            print("   NOTE not valid UTF-8, read as cp1252: %s"
                  % os.path.relpath(path, SEARCH_DIR))
        if STATUS not in df.columns:
            continue
        plan = fs.classify(df)
        counts = plan["counts"]
        totals.update(counts)
        totals["files"] += 1
        totals["rows"] += len(df)

        n_dd = len(plan["decisions"])
        if n_dd > worst[0]:
            worst = (n_dd, os.path.relpath(path, SEARCH_DIR))
        for key, idxs in plan["decision_rows"].items():
            all_pairs[key] += len(idxs)

        print("   %-58.58s rows=%-6d dropdowns=%d"
              % (os.path.relpath(path, SEARCH_DIR), len(df), n_dd))

        # --- 2. the accepted bucket must genuinely resolve to an enum
        for idx in plan["buckets"][fs.ACCEPTED]:
            row = df.loc[idx]
            state = str(row.get(STATE) or "").strip().upper()
            value = "" if pd.isna(row.get(STATUS)) else str(row.get(STATUS)).strip()
            if sfs.enum_for(state, value) is None:
                print("      FAIL accepted row {} ({} {!r}) has no enum"
                      .format(idx, state, value))
                failures += 1

        # --- 3. every punctuation repair must land on an accepted label
        for idx, canonical in plan["punctuation"].items():
            state = str(df.loc[idx].get(STATE) or "").strip().upper()
            if not sfs.is_accepted(state, canonical):
                print("      FAIL punctuation repair {} -> {!r} is not accepted in {}"
                      .format(idx, canonical, state))
                failures += 1

        # --- 4. regression against the pre-change tool, no mappings chosen
        _, csv_bytes, _, changes, _ = fs.apply_fixes(df, plan, {})
        new = pd.read_csv(io.BytesIO(csv_bytes), dtype=str).fillna("")
        old = old_tool_output(df).fillna("").astype(str)
        old = old.replace({"nan": "", "None": ""})

        if list(new.columns) != list(old.columns) or len(new) != len(old):
            print("      FAIL shape changed")
            failures += 1
            continue

        for col in new.columns:
            diff = new.index[new[col].str.strip() != old[col].str.strip()]
            if len(diff) == 0:
                continue
            if col != STATUS:
                print("      FAIL {} differs from the old tool on {} row(s)"
                      .format(col, len(diff)))
                failures += 1
                continue
            # Only the filing-status column may move, and only in two ways.
            for idx in diff:
                was = str(df.loc[idx].get(STATUS) or "").strip()
                if was in ("", "nan"):
                    # old wrote "Single", we now leave it or fill from a mapping
                    if new.at[idx, col].strip() not in ("", was):
                        print("      FAIL blank row {} became {!r}"
                              .format(idx, new.at[idx, col]))
                        failures += 1
                elif idx in plan["punctuation"]:
                    pass       # a deliberate repair
                else:
                    print("      FAIL non-blank row {} changed {!r} -> {!r}"
                          .format(idx, was, new.at[idx, col]))
                    failures += 1

        # --- 5. with mappings supplied, every mapped row must be written
        if plan["decisions"]:
            chosen = {}
            for (state, value) in plan["decisions"]:
                labels = sfs.accepted_labels(state)
                if labels:
                    chosen[(state, value)] = labels[0]
            _, csv2, _, changes2, review2 = fs.apply_fixes(df, plan, chosen)
            mapped = pd.read_csv(io.BytesIO(csv2), dtype=str).fillna("")
            for (state, value), label in chosen.items():
                for idx in plan["decision_rows"][(state, value)]:
                    if mapped.at[idx, STATUS].strip() != label:
                        print("      FAIL mapped row {} is {!r}, expected {!r}"
                              .format(idx, mapped.at[idx, STATUS], label))
                        failures += 1
            n_logged = (changes2["Column"] == STATUS).sum()
            n_expect = (sum(len(plan["decision_rows"][k]) for k in chosen)
                        + len(plan["punctuation"]))
            if n_logged != n_expect:
                print("      FAIL change log has {} filing-status rows, expected {}"
                      .format(n_logged, n_expect))
                failures += 1
            if (review2["Result"] == "Fixed").sum() != len(chosen):
                print("      FAIL review sheet does not show every pair fixed")
                failures += 1

    print()
    print("=" * 96)
    print("totals across %d file(s), %d rows" % (totals["files"], totals["rows"]))
    print("=" * 96)
    for bucket, label in fs.BUCKET_LABELS.items():
        print("   %-52s %d" % (label, totals[bucket]))
    print()
    print("   distinct (state, value) needing a decision : %d" % len(all_pairs))
    print("   worst single file                          : %d dropdown(s)  %s"
          % worst)
    print()
    for (state, value), n in all_pairs.most_common():
        print("   %-4s %-46.46s %5d" % (state, value or "(blank)", n))

    print()
    if failures:
        print("FAIL — %d problem(s)" % failures)
        return 1
    print("PASS — every check held on all %d file(s)" % totals["files"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
