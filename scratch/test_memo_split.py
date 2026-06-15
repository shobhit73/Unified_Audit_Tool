"""Tests for the 401k/Roth memo split in apps/adp/prior_payroll_sanity.py.

Replicates the Book1.xlsx toy example (sheet 1 in, sheet 2 expected) plus
edge cases: Roth-only file, ties, no-match counts, 0.00 entries, '-' cells.
Run from the repo root:  py scratch/test_memo_split.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from apps.adp.prior_payroll_sanity import (
    _is_entry,
    find_retirement_columns,
    detect_memo_split,
    split_memo_column,
)

failures = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        failures.append(name)


# ----- Book1.xlsx toy example ---------------------------------------------
MEMO = "Memo: 401k"
df = pd.DataFrame({
    "Employee Name": ["A", "B", "C", "D", "E"],
    "K-401K":  ["50", "",   "50", "50", ""],
    "R-Roth":  ["",   "50", "30", "20", ""],
    MEMO:      ["30", "30", "70", "40", ""],
})

k, r = find_retirement_columns(df)
check("find columns: K-401K", k == "K-401K", f"got {k}")
check("find columns: R-Roth", r == "R-Roth", f"got {r}")

info = detect_memo_split(df)
check("target = 4 (employees with K or Roth)", info["target"] == 4, str(info["target"]))
check("memo column matched", info["matches"] == [MEMO], str(info["matches"]))

out, split = split_memo_column(df, MEMO, info["k_col"])
new = split["new_col"]
check("new column name", new == f"Roth:{MEMO}", new)
check("new column right after memo", list(out.columns).index(new) == list(out.columns).index(MEMO) + 1)

# Expected (sheet 2): A memo 30 / roth blank; B memo blank / roth 30;
# C memo 50 / roth 20; D memo 40 / roth blank; E both blank.
def num(v):
    s = str(v).strip()
    return float(s) if s not in ("", "-", "nan") else None

memo_out = [num(v) for v in out[MEMO]]
roth_out = [num(v) for v in out[new]]
check("A: memo 30, roth blank", memo_out[0] == 30 and roth_out[0] is None, f"{memo_out[0]}/{roth_out[0]}")
check("B: memo blank, roth 30", memo_out[1] is None and roth_out[1] == 30, f"{memo_out[1]}/{roth_out[1]}")
check("C: memo 50, roth 20", memo_out[2] == 50 and roth_out[2] == 20, f"{memo_out[2]}/{roth_out[2]}")
check("D: memo 40, roth blank", memo_out[3] == 40 and roth_out[3] is None, f"{memo_out[3]}/{roth_out[3]}")
check("E: both blank", memo_out[4] is None and roth_out[4] is None, f"{memo_out[4]}/{roth_out[4]}")
check("rows_split = 2 (B and C)", split["rows_split"] == 2, str(split["rows_split"]))

# ----- Excess beyond K + Roth still all goes to Roth -----------------------
df2 = pd.DataFrame({
    "Employee Name": ["X"],
    "K-401K": ["50"],
    "R-Roth": ["10"],
    MEMO: ["100"],
})
out2, _ = split_memo_column(df2, MEMO, "K-401K")
check("excess beyond K+Roth -> all to Roth", num(out2[MEMO][0]) == 50 and num(out2[f"Roth:{MEMO}"][0]) == 50)

# ----- Roth-only file: K missing -> everything moves ------------------------
df3 = pd.DataFrame({
    "Employee Name": ["A", "B"],
    "R-Roth": ["50", ""],
    "Memo: Match": ["30", ""],
})
info3 = detect_memo_split(df3)
check("roth-only: k_col None, match found", info3["k_col"] is None and info3["matches"] == ["Memo: Match"])
out3, split3 = split_memo_column(df3, "Memo: Match", info3["k_col"])
check("roth-only: memo moved entirely",
      num(out3["Memo: Match"][0]) is None and num(out3["Roth:Memo: Match"][0]) == 30)

# ----- Tie: two memo columns with the same matching count -------------------
df4 = pd.DataFrame({
    "Employee Name": ["A", "B"],
    "Voluntary K-401K": ["50", "20"],
    "R-ROTH": ["", "10"],
    "Memo: One": ["5", "5"],
    "Memo: Two": ["7", "7"],
})
info4 = detect_memo_split(df4)
check("tie: both memo columns match", sorted(info4["matches"]) == ["Memo: One", "Memo: Two"], str(info4["matches"]))
check("tie: full header variants found",
      info4["k_col"] == "Voluntary K-401K" and info4["roth_col"] == "R-ROTH")

# ----- No match: counts reported --------------------------------------------
df5 = pd.DataFrame({
    "Employee Name": ["A", "B", "C"],
    "K-401K": ["50", "20", ""],
    "Memo: Other": ["1", "", ""],
})
info5 = detect_memo_split(df5)
check("no match: empty matches, counts kept",
      info5["matches"] == [] and info5["memo_counts"] == {"Memo: Other": 1} and info5["target"] == 2)

# ----- Entry semantics: 0.00 counts, '-' and blanks don't -------------------
check("0.00 is an entry", _is_entry("0.00") and _is_entry(0.0))
check("'-' / '' / NaN are not entries",
      not _is_entry("-") and not _is_entry("") and not _is_entry(float("nan")) and not _is_entry(None))

# Aggregated-style values (floats with NaN) also count correctly
df6 = pd.DataFrame({
    "Employee Name": ["A", "B"],
    "K-401K": [50.0, float("nan")],
    "R-Roth": [float("nan"), 25.0],
    "Memo: M": [10.0, 12.5],
})
info6 = detect_memo_split(df6)
check("float/NaN frame: target 2, match", info6["target"] == 2 and info6["matches"] == ["Memo: M"])

# Memo column must never be picked as a deduction column
df7 = pd.DataFrame({"Memo: 401k": ["1"], "Memo: Roth": ["2"]})
check("memo-only file -> not applicable", detect_memo_split(df7) is None)

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("All tests passed.")
