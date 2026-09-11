# ADP Qualified Overtime Wages — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill UZIO's Qualified Overtime import template from ADP prior payroll files — one row per employee per pay period that carries a qualified-overtime premium.

**Architecture:** One new self-contained module, `apps/adp/qualified_overtime.py`, exposing pure functions (read → resolve column → build rows → write workbook) plus a `render_ui()` that the existing `app.py` router calls. No existing module is modified except `app.py`, which gains one sidebar entry and one routing branch.

**Tech Stack:** Python 3.13, pandas, openpyxl, Streamlit. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-03-adp-qualified-overtime-design.md`

## Global Constraints

- **This repo has no pytest and no `tests/` directory.** Its convention is standalone verification scripts under `scratch/` (which IS tracked in git — ~80 such scripts are committed). Every task below writes one, runs it to see it fail, implements, and runs it to see it pass.
- Source data is read with `dtype=str` — never let pandas coerce IDs or dates.
- Dates are written **verbatim from the source**, `MM/DD/YYYY`. No reformatting.
- Never write a UTF-8 BOM. (No CSV is produced here, but the rule is repo-wide.)
- Uploaded files are `BytesIO`-like — call `.seek(0)` before every re-read.
- ADP only. Do not touch `apps/paycom/`.
- Mirror rule: any `apps/**` change must also be mirrored into `implementors_repo/`. That folder is an empty stub on this machine, so the mirror cannot be done here — flag it at the end instead of silently skipping it.
- Do not `git push`. Commit only.

## Reference data used by every verification script

```
CDC = r"C:\Users\rohit.kaushik\Downloads\CDC"
TEMPLATE = CDC + r"\Qualified_Overtime_Template_2026.xlsx"
PAYROLL  = [CDC + r"\Payroll\Cleaned\Payroll History_Q3_cleaned.csv",
            CDC + r"\Payroll\Cleaned\PriorPayroll_03222026_06202026_06262026_cleaned.csv",
            CDC + r"\Payroll\Cleaned\PriorPayroll_12212025_03212026_03272026_cleaned.csv"]
```

Known-good expected values for this client, measured from the data:

| | value |
|---|---|
| payroll rows combined | 1692 |
| employees in payroll | 294 |
| rows emitted (QOT ≠ 0) | 289 |
| employees emitted | 117 |
| employees dropped (all zero/blank) | 177 |
| total QOT | 13589.77 |
| overlapping period pairs | 0 |
| emitted employees absent from template | 0 |
| template employees | 284 |

## File structure

| File | Responsibility |
|---|---|
| `apps/adp/qualified_overtime.py` (create) | Everything: constants, readers, row builder, workbook writer, `render_ui()` |
| `app.py` (modify) | One sidebar list entry, one `elif` routing branch |
| `scratch/verify_qot_*.py` (create, 4 files) | Per-task verification scripts |

---

### Task 1: Read payroll files and resolve the QOT column

**Files:**
- Create: `apps/adp/qualified_overtime.py`
- Test: `scratch/verify_qot_read.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `QOT_DEFAULT_COLUMN = "MEMO : $R-FDQOT"`, `ADP_ID_COL`, `ADP_START_COL`, `ADP_END_COL`, `ADP_PAY_COL`
  - `read_payroll_files(files) -> (pd.DataFrame, list[str])` — concatenated frame with an added `_file` column, plus a list of human-readable errors
  - `memo_columns(df) -> list[str]` — every column whose name starts with `MEMO` (case-insensitive), sorted, excluding `TOTAL MEMOS`
  - `resolve_qot_column(df, chosen=None) -> (str|None, dict)` — returns the column to use and `{filename: True/False}` saying which files carry it

- [ ] **Step 1: Write the failing verification script**

Create `scratch/verify_qot_read.py`:

```python
"""Task 1 — payroll reading + QOT column resolution."""
import io
import os
import sys

sys.path.insert(0, r"C:\Users\rohit.kaushik\Downloads\Unified_Audit_Tool")
import apps.adp.qualified_overtime as Q

CDC = r"C:\Users\rohit.kaushik\Downloads\CDC"
PAYROLL = [CDC + r"\Payroll\Cleaned\Payroll History_Q3_cleaned.csv",
           CDC + r"\Payroll\Cleaned\PriorPayroll_03222026_06202026_06262026_cleaned.csv",
           CDC + r"\Payroll\Cleaned\PriorPayroll_12212025_03212026_03272026_cleaned.csv"]


class Upload(io.BytesIO):
    def __init__(self, path):
        super().__init__(open(path, "rb").read())
        self.name = os.path.basename(path)
        self.size = self.getbuffer().nbytes


ok = True


def check(label, got, want):
    global ok
    good = got == want
    ok = ok and good
    print("   %-46s %-28r %s" % (label, got, "OK" if good else "FAIL, want %r" % (want,)))


df, errors = Q.read_payroll_files([Upload(p) for p in PAYROLL])
check("rows", len(df), 1692)
check("errors", errors, [])
check("employees", df[Q.ADP_ID_COL].nunique(), 294)
check("_file column present", "_file" in df.columns, True)
check("id is string", isinstance(df[Q.ADP_ID_COL].iloc[0], str), True)

col, per_file = Q.resolve_qot_column(df)
check("resolved column", col, Q.QOT_DEFAULT_COLUMN)
check("all three files have it", sorted(per_file.values()), [True, True, True])

memos = Q.memo_columns(df)
check("TOTAL MEMOS excluded", "TOTAL MEMOS" in memos, False)
check("default column listed", Q.QOT_DEFAULT_COLUMN in memos, True)

# when the real column is absent, nothing is resolved and the caller must ask
stripped = df.drop(columns=[Q.QOT_DEFAULT_COLUMN])
col2, _ = Q.resolve_qot_column(stripped)
check("absent -> None", col2, None)
check("explicit choice honoured",
      Q.resolve_qot_column(stripped, chosen="MEMO : PTO-PAID TIME OFF")[0],
      "MEMO : PTO-PAID TIME OFF")

print()
print("TASK 1", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
py scratch/verify_qot_read.py
```

Expected: `ModuleNotFoundError: No module named 'apps.adp.qualified_overtime'`

- [ ] **Step 3: Create the module with just these pieces**

Create `apps/adp/qualified_overtime.py`:

```python
import io
import os
import re

import pandas as pd
import streamlit as st

APP_TITLE = "ADP - Qualified Overtime Wages"

# Prior payroll (ADP) column names.
ADP_ID_COL = "ASSOCIATE ID"
ADP_START_COL = "PERIOD BEGINNING DATE"
ADP_END_COL = "PERIOD ENDING DATE"
ADP_PAY_COL = "PAY DATE"
QOT_DEFAULT_COLUMN = "MEMO : $R-FDQOT"

ADP_REQUIRED_COLUMNS = [ADP_ID_COL, ADP_START_COL, ADP_END_COL, ADP_PAY_COL]


def _read_one(file):
    """Read an uploaded payroll file as strings. Returns (df, error)."""
    name = (getattr(file, "name", "") or "")
    file.seek(0)
    raw = file.read()
    buf = io.BytesIO(raw)
    try:
        if name.lower().endswith(".csv"):
            df = pd.read_csv(buf, dtype=str, low_memory=False)
        else:
            df = pd.read_excel(buf, dtype=str)
    except Exception as e:
        return None, "%s — could not be read: %s" % (name, e)
    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in ADP_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return None, "%s — missing column(s): %s" % (name, ", ".join(missing))
    df["_file"] = name
    return df, None


def read_payroll_files(files):
    """Concatenate the uploaded prior payroll files.

    Returns (DataFrame, errors). A file that cannot be read, or that lacks one
    of the four columns this module needs, is reported and left out rather than
    failing the whole run — the others still carry usable data.
    """
    frames, errors = [], []
    for f in files or []:
        df, err = _read_one(f)
        if err:
            errors.append(err)
        else:
            frames.append(df)
    if not frames:
        return pd.DataFrame(), errors
    out = pd.concat(frames, ignore_index=True)
    out[ADP_ID_COL] = out[ADP_ID_COL].fillna("").astype(str).str.strip()
    return out, errors


def memo_columns(df):
    """Every MEMO column the user could pick from, minus the roll-up total."""
    return sorted(c for c in df.columns
                  if str(c).strip().upper().startswith("MEMO")
                  and str(c).strip().upper() != "TOTAL MEMOS")


def resolve_qot_column(df, chosen=None):
    """Which column holds the qualified-overtime premium.

    `chosen` is the user's dropdown pick and always wins. Otherwise the ADP
    default is used when present. Returns (column_or_None, {file: present?}) so
    the UI can name the files that will be skipped.
    """
    col = chosen or (QOT_DEFAULT_COLUMN if QOT_DEFAULT_COLUMN in df.columns else None)
    per_file = {}
    if col and "_file" in df.columns:
        for name, g in df.groupby("_file"):
            per_file[name] = bool(g[col].notna().any()) if col in g.columns else False
    return col, per_file
```

- [ ] **Step 4: Run it to confirm it passes**

```bash
py scratch/verify_qot_read.py
```

Expected: every line `OK`, final line `TASK 1 PASS`, exit code 0.

- [ ] **Step 5: Commit**

```bash
git add apps/adp/qualified_overtime.py scratch/verify_qot_read.py
git commit -m "feat(adp-qot): read prior payroll files and resolve the QOT column"
```

---

### Task 2: Read the UZIO template

**Files:**
- Modify: `apps/adp/qualified_overtime.py`
- Test: `scratch/verify_qot_template.py`

**Interfaces:**
- Consumes: Task 1's module
- Produces:
  - `TEMPLATE_SHEET = "QOT Details"`, `TEMPLATE_HEADERS` (the 8 headers in order)
  - `read_qot_template(file) -> (pd.DataFrame, str|None)` — the sheet as strings, or `(None, error)`

- [ ] **Step 1: Write the failing verification script**

Create `scratch/verify_qot_template.py`:

```python
"""Task 2 — reading the UZIO Qualified Overtime template."""
import io
import os
import sys

import pandas as pd

sys.path.insert(0, r"C:\Users\rohit.kaushik\Downloads\Unified_Audit_Tool")
import apps.adp.qualified_overtime as Q

CDC = r"C:\Users\rohit.kaushik\Downloads\CDC"
TEMPLATE = CDC + r"\Qualified_Overtime_Template_2026.xlsx"


class Upload(io.BytesIO):
    def __init__(self, path):
        super().__init__(open(path, "rb").read())
        self.name = os.path.basename(path)
        self.size = self.getbuffer().nbytes


ok = True


def check(label, got, want):
    global ok
    good = got == want
    ok = ok and good
    print("   %-44s %-30r %s" % (label, got, "OK" if good else "FAIL, want %r" % (want,)))


tpl, err = Q.read_qot_template(Upload(TEMPLATE))
check("no error", err, None)
check("employees", len(tpl), 284)
check("headers", list(tpl.columns), Q.TEMPLATE_HEADERS)
check("ids are strings", isinstance(tpl["Employee ID"].iloc[0], str), True)
check("first id", tpl["Employee ID"].iloc[0], "067PC9FLL")
check("status values", sorted(tpl["Employment Status"].unique()), ["Active", "Terminated"])

# a workbook with no QOT Details sheet must be refused, not guessed at
bad = io.BytesIO()
pd.DataFrame({"a": [1]}).to_excel(bad, index=False, sheet_name="Something Else")
bad.seek(0)
bad.name = "bad.xlsx"
tpl2, err2 = Q.read_qot_template(bad)
check("bad workbook -> None", tpl2, None)
check("bad workbook -> error", isinstance(err2, str) and "QOT Details" in err2, True)

print()
print("TASK 2", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
py scratch/verify_qot_template.py
```

Expected: `AttributeError: module 'apps.adp.qualified_overtime' has no attribute 'read_qot_template'`

- [ ] **Step 3: Add the template reader**

Append to `apps/adp/qualified_overtime.py`:

```python
# UZIO Qualified Overtime template. Headers sit on row 1 of "QOT Details";
# "Instructions" is a second sheet that must survive into the output untouched.
TEMPLATE_SHEET = "QOT Details"
TEMPLATE_HEADERS = ["Employee ID", "First Name", "Last Name", "Employment Status",
                    "Period Start Date", "Period End Date", "Pay Date", "QOT Premium"]


def read_qot_template(file):
    """Read the template's QOT Details sheet as strings. Returns (df, error)."""
    file.seek(0)
    try:
        book = pd.read_excel(io.BytesIO(file.read()), sheet_name=None, dtype=str)
    except Exception as e:
        return None, "Could not read the template: %s" % e
    if TEMPLATE_SHEET not in book:
        return None, ("The template has no `%s` sheet. Sheets found: %s."
                      % (TEMPLATE_SHEET, ", ".join(book) or "none"))
    df = book[TEMPLATE_SHEET].copy()
    df.columns = [str(c).strip() for c in df.columns]
    missing = [h for h in TEMPLATE_HEADERS if h not in df.columns]
    if missing:
        return None, ("`%s` is missing column(s): %s."
                      % (TEMPLATE_SHEET, ", ".join(missing)))
    df = df[TEMPLATE_HEADERS].copy()
    df["Employee ID"] = df["Employee ID"].fillna("").astype(str).str.strip()
    df = df[df["Employee ID"] != ""].reset_index(drop=True)
    return df.fillna(""), None
```

- [ ] **Step 4: Run it to confirm it passes**

```bash
py scratch/verify_qot_template.py
```

Expected: every line `OK`, final line `TASK 2 PASS`, exit code 0.

- [ ] **Step 5: Commit**

```bash
git add apps/adp/qualified_overtime.py scratch/verify_qot_template.py
git commit -m "feat(adp-qot): read the UZIO Qualified Overtime template"
```

---

### Task 3: Build the rows and run the validations

**Files:**
- Modify: `apps/adp/qualified_overtime.py`
- Test: `scratch/verify_qot_rows.py`

**Interfaces:**
- Consumes: `read_payroll_files`, `read_qot_template`, `resolve_qot_column`
- Produces:
  - `build_qot_rows(payroll_df, template_df, qot_col) -> dict` with keys:
    - `rows` — `list[dict]`, each keyed by `TEMPLATE_HEADERS`, sorted by Employee ID then Pay Date
    - `overlaps` — `list[dict]` with `Employee ID`, `Period A`, `File A`, `Period B`, `File B`
    - `missing_dates` — `list[dict]` with `Employee ID`, `Pay Date`, `Missing`
    - `not_in_template` — `list[dict]` with `Employee ID`, `Rows`, `Total QOT`
    - `employees_emitted` (int), `employees_dropped_zero` (int), `total_qot` (float)
  - `is_blocked(result) -> bool` — True when `overlaps` or `missing_dates` is non-empty

- [ ] **Step 1: Write the failing verification script**

Create `scratch/verify_qot_rows.py`:

```python
"""Task 3 — row building, the zero filter, and the blocking validations."""
import io
import os
import sys

import pandas as pd

sys.path.insert(0, r"C:\Users\rohit.kaushik\Downloads\Unified_Audit_Tool")
import apps.adp.qualified_overtime as Q

CDC = r"C:\Users\rohit.kaushik\Downloads\CDC"
TEMPLATE = CDC + r"\Qualified_Overtime_Template_2026.xlsx"
PAYROLL = [CDC + r"\Payroll\Cleaned\Payroll History_Q3_cleaned.csv",
           CDC + r"\Payroll\Cleaned\PriorPayroll_03222026_06202026_06262026_cleaned.csv",
           CDC + r"\Payroll\Cleaned\PriorPayroll_12212025_03212026_03272026_cleaned.csv"]


class Upload(io.BytesIO):
    def __init__(self, path):
        super().__init__(open(path, "rb").read())
        self.name = os.path.basename(path)
        self.size = self.getbuffer().nbytes


ok = True


def check(label, got, want):
    global ok
    good = got == want
    ok = ok and good
    print("   %-46s %-24r %s" % (label, got, "OK" if good else "FAIL, want %r" % (want,)))


pay, _ = Q.read_payroll_files([Upload(p) for p in PAYROLL])
tpl, _ = Q.read_qot_template(Upload(TEMPLATE))
col, _ = Q.resolve_qot_column(pay)
res = Q.build_qot_rows(pay, tpl, col)

print("CDC, whole client:")
check("rows emitted", len(res["rows"]), 289)
check("employees emitted", res["employees_emitted"], 117)
check("employees dropped as zero", res["employees_dropped_zero"], 177)
check("total qot", round(res["total_qot"], 2), 13589.77)
check("overlaps", res["overlaps"], [])
check("missing dates", res["missing_dates"], [])
check("not in template", res["not_in_template"], [])
check("not blocked", Q.is_blocked(res), False)

r0 = res["rows"][0]
check("row keys", list(r0), Q.TEMPLATE_HEADERS)
check("dates verbatim", r0["Pay Date"], "03/27/2026")

print()
print("the three cases from the spec:")
by_emp = {}
for r in res["rows"]:
    by_emp.setdefault(r["Employee ID"], []).append(r)
# 11 paychecks, exactly one with a premium
check("14907Q48A rows", len(by_emp.get("14907Q48A", [])), 1)
check("14907Q48A premium", by_emp["14907Q48A"][0]["QOT Premium"], 36.34)
# 11 paychecks, ten with a premium
check("MY0KMI29H rows", len(by_emp.get("MY0KMI29H", [])), 10)
# no premium at all -> absent entirely
check("067PC9FLL absent", "067PC9FLL" in by_emp, False)

print()
print("synthetic blocking cases:")
tiny_tpl = pd.DataFrame([{"Employee ID": "E1", "First Name": "A", "Last Name": "B",
                          "Employment Status": "Active", "Period Start Date": "",
                          "Period End Date": "", "Pay Date": "", "QOT Premium": ""}])


def frame(rows):
    return pd.DataFrame([{Q.ADP_ID_COL: e, Q.ADP_START_COL: s, Q.ADP_END_COL: en,
                          Q.ADP_PAY_COL: p, Q.QOT_DEFAULT_COLUMN: v, "_file": f}
                         for e, s, en, p, v, f in rows])


overlap = frame([("E1", "01/01/2026", "03/31/2026", "04/03/2026", "10", "a.csv"),
                 ("E1", "03/01/2026", "03/07/2026", "03/13/2026", "5", "b.csv")])
r = Q.build_qot_rows(overlap, tiny_tpl, Q.QOT_DEFAULT_COLUMN)
check("overlap detected", len(r["overlaps"]), 1)
check("overlap blocks", Q.is_blocked(r), True)

same = frame([("E1", "01/01/2026", "01/07/2026", "01/09/2026", "10", "a.csv"),
              ("E1", "01/01/2026", "01/07/2026", "01/09/2026", "10", "b.csv")])
check("same period in two files blocks",
      Q.is_blocked(Q.build_qot_rows(same, tiny_tpl, Q.QOT_DEFAULT_COLUMN)), True)

partial = frame([("E1", "01/01/2026", "", "01/09/2026", "10", "a.csv")])
r = Q.build_qot_rows(partial, tiny_tpl, Q.QOT_DEFAULT_COLUMN)
check("missing one date detected", len(r["missing_dates"]), 1)
check("missing date blocks", Q.is_blocked(r), True)

negative = frame([("E1", "01/01/2026", "01/07/2026", "01/09/2026", "-4.50", "a.csv")])
check("negative premium kept",
      len(Q.build_qot_rows(negative, tiny_tpl, Q.QOT_DEFAULT_COLUMN)["rows"]), 1)

check("CDC pay years", res["pay_years"], [2026])
two_years = frame([("E1", "12/20/2025", "12/26/2025", "01/02/2026", "10", "a.csv"),
                   ("E1", "01/03/2026", "01/09/2026", "01/16/2026", "10", "a.csv"),
                   ("E1", "12/01/2024", "12/07/2024", "12/12/2024", "10", "a.csv")])
check("multiple pay years surfaced",
      Q.build_qot_rows(two_years, tiny_tpl, Q.QOT_DEFAULT_COLUMN)["pay_years"], [2024, 2026])
check("multiple pay years do NOT block",
      Q.is_blocked(Q.build_qot_rows(two_years, tiny_tpl, Q.QOT_DEFAULT_COLUMN)), False)

orphan = frame([("E9", "01/01/2026", "01/07/2026", "01/09/2026", "10", "a.csv")])
r = Q.build_qot_rows(orphan, tiny_tpl, Q.QOT_DEFAULT_COLUMN)
check("orphan not emitted", len(r["rows"]), 0)
check("orphan reported", len(r["not_in_template"]), 1)
check("orphan does not block", Q.is_blocked(r), False)

print()
print("TASK 3", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
py scratch/verify_qot_rows.py
```

Expected: `AttributeError: module 'apps.adp.qualified_overtime' has no attribute 'build_qot_rows'`

- [ ] **Step 3: Add the row builder and validations**

Append to `apps/adp/qualified_overtime.py`:

```python
def _money(v):
    """Parse a premium. Blank / unparseable -> None, which means 'no overtime'."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip().replace(",", "").replace("$", "")
    if s == "" or s.lower() in ("nan", "none"):
        return None
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def build_qot_rows(payroll_df, template_df, qot_col):
    """One output row per (employee, pay date) whose premium is non-zero.

    The filter is per ROW, not per employee: an employee keeps every pay period
    that carries a premium and disappears only when all of theirs are zero or
    blank. Rule 14 of the template ("omission does not delete") makes dropping
    the zero rows safe.

    Blank and 0 both mean "no qualified overtime". A NEGATIVE premium is kept —
    non-zero in either direction is real data.
    """
    empty = {"rows": [], "overlaps": [], "missing_dates": [], "not_in_template": [],
             "employees_emitted": 0, "employees_dropped_zero": 0, "total_qot": 0.0}
    if payroll_df.empty or qot_col not in payroll_df.columns:
        return empty

    df = payroll_df.copy()
    df["_qot"] = df[qot_col].apply(_money)
    all_employees = set(df[ADP_ID_COL]) - {""}
    kept = df[df["_qot"].notna() & (df["_qot"] != 0)].copy()

    names = template_df.set_index("Employee ID")[
        ["First Name", "Last Name", "Employment Status"]].to_dict("index")

    # `row_files` runs parallel to `rows` so the overlap report can name the file
    # each side came from. It cannot live inside the row dicts: those are keyed
    # strictly by TEMPLATE_HEADERS.
    rows, row_files, missing_dates, orphan = [], [], {}, {}
    for _, r in kept.iterrows():
        eid = r[ADP_ID_COL]
        start, end, pay = (str(r[c]).strip() if pd.notna(r[c]) else ""
                           for c in (ADP_START_COL, ADP_END_COL, ADP_PAY_COL))

        # Template rule 5: a row must carry all three dates or none. We always
        # write dates, so a row short of one is unusable and blocks the run.
        absent = [lbl for lbl, val in (("Period Start Date", start),
                                       ("Period End Date", end),
                                       ("Pay Date", pay)) if not val]
        if absent:
            missing_dates.setdefault((eid, pay), {
                "Employee ID": eid, "Pay Date": pay or "(blank)",
                "Missing": ", ".join(absent)})
            continue

        if eid not in names:
            # UZIO has no such employee to import against, so the row is left
            # out — but the money is real, so it is reported.
            o = orphan.setdefault(eid, {"Employee ID": eid, "Rows": 0, "Total QOT": 0.0})
            o["Rows"] += 1
            o["Total QOT"] = round(o["Total QOT"] + r["_qot"], 2)
            continue

        n = names[eid]
        rows.append({
            "Employee ID": eid,
            "First Name": n.get("First Name", ""),
            "Last Name": n.get("Last Name", ""),
            "Employment Status": n.get("Employment Status", ""),
            "Period Start Date": start,
            "Period End Date": end,
            "Pay Date": pay,
            "QOT Premium": r["_qot"],
        })
        row_files.append(str(r.get("_file", "")))

    order = sorted(range(len(rows)),
                   key=lambda i: (rows[i]["Employee ID"],
                                  pd.to_datetime(rows[i]["Pay Date"], errors="coerce")))
    rows = [rows[i] for i in order]
    row_files = [row_files[i] for i in order]

    emitted = {r["Employee ID"] for r in rows}
    pay_years = sorted({d.year for d in
                        pd.to_datetime([r["Pay Date"] for r in rows], errors="coerce")
                        if pd.notna(d)})
    return {
        "rows": rows,
        "overlaps": _find_overlaps(rows, row_files),
        "missing_dates": list(missing_dates.values()),
        "not_in_template": sorted(orphan.values(), key=lambda x: x["Employee ID"]),
        "employees_emitted": len(emitted),
        "employees_dropped_zero": len(all_employees - emitted - set(orphan)),
        "total_qot": round(sum(r["QOT Premium"] for r in rows), 2),
        "pay_years": pay_years,
    }


def _find_overlaps(rows, row_files):
    """Template rule 9: rows for the same employee must not overlap.

    UZIO rejects an import that contains overlapping periods, so this blocks
    rather than warns. Two copies of the same paycheck from two uploaded files
    produce identical periods and are caught here too — the tool cannot know
    which copy is authoritative, and picking one would be a guess.
    """
    by_emp = {}
    for r, src in zip(rows, row_files):
        by_emp.setdefault(r["Employee ID"], []).append((r, src))

    out = []
    for eid, group in by_emp.items():
        dated = []
        for r, src in group:
            s = pd.to_datetime(r["Period Start Date"], errors="coerce")
            e = pd.to_datetime(r["Period End Date"], errors="coerce")
            if pd.notna(s) and pd.notna(e):
                dated.append((s, e, r, src))
        dated.sort(key=lambda x: (x[0], x[1]))
        for i in range(1, len(dated)):
            _, pe, prev, prev_src = dated[i - 1]
            cs, _, cur, cur_src = dated[i]
            if cs <= pe:
                out.append({
                    "Employee ID": eid,
                    "Period A": "%s .. %s" % (prev["Period Start Date"], prev["Period End Date"]),
                    "File A": prev_src,
                    "Period B": "%s .. %s" % (cur["Period Start Date"], cur["Period End Date"]),
                    "File B": cur_src,
                })
    return out


def is_blocked(result):
    """Overlapping periods or a part-dated row make the file unimportable."""
    return bool(result["overlaps"] or result["missing_dates"])
```

- [ ] **Step 4: Run it to confirm it passes**

```bash
py scratch/verify_qot_rows.py
```

Expected: every line `OK`, final line `TASK 3 PASS`, exit code 0.

- [ ] **Step 5: Commit**

```bash
git add apps/adp/qualified_overtime.py scratch/verify_qot_rows.py
git commit -m "feat(adp-qot): build rows per pay period with overlap and date validation"
```

---

### Task 4: Write the filled workbook

**Files:**
- Modify: `apps/adp/qualified_overtime.py`
- Test: `scratch/verify_qot_workbook.py`

**Interfaces:**
- Consumes: `build_qot_rows`
- Produces:
  - `fill_qot_template(template_file, rows) -> bytes`
  - `output_filename(client_name, template_file) -> str`

- [ ] **Step 1: Write the failing verification script**

Create `scratch/verify_qot_workbook.py`:

```python
"""Task 4 — writing the filled template."""
import io
import os
import sys

import openpyxl
import pandas as pd

sys.path.insert(0, r"C:\Users\rohit.kaushik\Downloads\Unified_Audit_Tool")
import apps.adp.qualified_overtime as Q

CDC = r"C:\Users\rohit.kaushik\Downloads\CDC"
TEMPLATE = CDC + r"\Qualified_Overtime_Template_2026.xlsx"
PAYROLL = [CDC + r"\Payroll\Cleaned\Payroll History_Q3_cleaned.csv",
           CDC + r"\Payroll\Cleaned\PriorPayroll_03222026_06202026_06262026_cleaned.csv",
           CDC + r"\Payroll\Cleaned\PriorPayroll_12212025_03212026_03272026_cleaned.csv"]


class Upload(io.BytesIO):
    def __init__(self, path):
        super().__init__(open(path, "rb").read())
        self.name = os.path.basename(path)
        self.size = self.getbuffer().nbytes


ok = True


def check(label, got, want):
    global ok
    good = got == want
    ok = ok and good
    print("   %-50s %-46r %s" % (label, got, "OK" if good else "FAIL, want %r" % (want,)))


pay, _ = Q.read_payroll_files([Upload(p) for p in PAYROLL])
tpl, _ = Q.read_qot_template(Upload(TEMPLATE))
col, _ = Q.resolve_qot_column(pay)
res = Q.build_qot_rows(pay, tpl, col)

data = Q.fill_qot_template(Upload(TEMPLATE), res["rows"])
wb = openpyxl.load_workbook(io.BytesIO(data))
src = openpyxl.load_workbook(TEMPLATE)
check("sheet list preserved", wb.sheetnames, src.sheetnames)
check("Instructions kept", "Instructions" in wb.sheetnames, True)

ws = wb[Q.TEMPLATE_SHEET]
check("header row intact",
      [ws.cell(row=1, column=i + 1).value for i in range(8)], Q.TEMPLATE_HEADERS)
check("row count = emitted rows", ws.max_row - 1, 289)

out = pd.read_excel(io.BytesIO(data), sheet_name=Q.TEMPLATE_SHEET, dtype=str)
check("no blank template rows left", int(out["Pay Date"].fillna("").eq("").sum()), 0)
check("every row has all three dates",
      int(out[["Period Start Date", "Period End Date", "Pay Date"]]
          .fillna("").eq("").any(axis=1).sum()), 0)
check("total premium",
      round(pd.to_numeric(out["QOT Premium"]).sum(), 2), 13589.77)
check("first employee", out["Employee ID"].iloc[0], "11M4UJ5DM")

check("filename", Q.output_filename("CDC", Upload(TEMPLATE)),
      "CDC_Qualified_Overtime_Template_2026_filled.xlsx")

print()
print("TASK 4", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
py scratch/verify_qot_workbook.py
```

Expected: `AttributeError: module 'apps.adp.qualified_overtime' has no attribute 'fill_qot_template'`

- [ ] **Step 3: Add the workbook writer**

Append to `apps/adp/qualified_overtime.py`:

```python
def fill_qot_template(template_file, rows):
    """Write the rows into a copy of the uploaded template. Returns .xlsx bytes.

    Opened through openpyxl so the Instructions sheet and all formatting survive.
    The template's pre-filled rows are cleared first: left in place they would be
    DATELESS rows with a blank premium, and template rule 12 makes a dateless row
    the employee's cumulative total, replacing everything already imported for
    them. Only the rows this tool fills are written.
    """
    template_file.seek(0)
    wb = openpyxl.load_workbook(io.BytesIO(template_file.read()))
    ws = wb[TEMPLATE_SHEET]

    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row - 1)

    for i, r in enumerate(rows, start=2):
        for j, h in enumerate(TEMPLATE_HEADERS, start=1):
            ws.cell(row=i, column=j).value = r[h]

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def output_filename(client_name, template_file):
    """<Client>_<uploaded template's name>_filled.xlsx"""
    base = os.path.splitext(getattr(template_file, "name", "") or "template")[0]
    client = re.sub(r"\s+", " ", str(client_name or "Client")).strip() or "Client"
    return "%s_%s_filled.xlsx" % (client, base)
```

Add `import openpyxl` to the imports at the top of the module.

- [ ] **Step 4: Run it to confirm it passes**

```bash
py scratch/verify_qot_workbook.py
```

Expected: every line `OK`, final line `TASK 4 PASS`, exit code 0.

- [ ] **Step 5: Commit**

```bash
git add apps/adp/qualified_overtime.py scratch/verify_qot_workbook.py
git commit -m "feat(adp-qot): write the filled template, preserving Instructions and formatting"
```

---

### Task 5: Streamlit UI and routing

**Files:**
- Modify: `apps/adp/qualified_overtime.py`
- Modify: `app.py` (sidebar list around line 136, routing branch around line 205)
- Test: manual, in the running app

**Interfaces:**
- Consumes: everything above
- Produces: `render_ui()`

- [ ] **Step 1: Add `render_ui()`**

Append to `apps/adp/qualified_overtime.py`:

```python
def render_ui():
    st.title(APP_TITLE)
    st.markdown("""
    **Upload**
    1. **ADP Prior Payroll file(s)** — as many as needed (.csv, .xls, .xlsx)
    2. **UZIO Qualified Overtime template** (.xlsx)

    One row is written per employee per pay period that carries a qualified
    overtime premium. Pay periods with no premium are left out — template rule 14
    says omission never deletes anything already in UZIO.
    """)

    client_name = st.text_input("Client Name", value="Client", key="qot_client")
    c1, c2 = st.columns(2)
    with c1:
        pay_files = st.file_uploader("ADP Prior Payroll file(s)",
                                     type=["csv", "xls", "xlsx"],
                                     accept_multiple_files=True, key="qot_pay")
    with c2:
        tpl_file = st.file_uploader("UZIO Qualified Overtime template",
                                    type=["xlsx"], key="qot_tpl")

    if not pay_files or not tpl_file:
        st.info("Upload the prior payroll file(s) and the UZIO template to begin.")
        return

    payroll, read_errors = read_payroll_files(pay_files)
    for e in read_errors:
        st.warning(e)
    if payroll.empty:
        st.error("None of the uploaded payroll files could be used.")
        return

    template, tpl_err = read_qot_template(tpl_file)
    if tpl_err:
        st.error(tpl_err)
        return

    # The premium column: use ADP's default when it is there, otherwise ask.
    chosen = None
    if QOT_DEFAULT_COLUMN not in payroll.columns:
        options = memo_columns(payroll)
        if not options:
            st.error("No `MEMO` columns found in the uploaded payroll files, so the "
                     "qualified overtime premium cannot be located.")
            return
        st.warning("`%s` was not found in any uploaded file. Pick the column that "
                   "holds the qualified overtime premium." % QOT_DEFAULT_COLUMN)
        chosen = st.selectbox("Qualified overtime column", options, key="qot_col")

    qot_col, per_file = resolve_qot_column(payroll, chosen)
    skipped = [f for f, present in per_file.items() if not present]
    if skipped:
        st.warning("No `%s` values in: %s. Those files contribute nothing."
                   % (qot_col, ", ".join(skipped)))

    result = build_qot_rows(payroll, template, qot_col)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Rows to import", len(result["rows"]))
    m2.metric("Employees", result["employees_emitted"])
    m3.metric("Total QOT", "%.2f" % result["total_qot"])
    m4.metric("Dropped (no overtime)", result["employees_dropped_zero"])

    if result["missing_dates"]:
        st.error("**%d row(s) are missing a date.** The template requires all three "
                 "dates or none, so no file was produced."
                 % len(result["missing_dates"]))
        st.dataframe(pd.DataFrame(result["missing_dates"]),
                     hide_index=True, use_container_width=True)

    if result["overlaps"]:
        st.error("**%d overlapping period(s).** UZIO rejects an import whose rows "
                 "overlap for the same employee, so no file was produced. This "
                 "usually means a quarterly file and the weekly files covering the "
                 "same quarter were both uploaded." % len(result["overlaps"]))
        st.dataframe(pd.DataFrame(result["overlaps"]),
                     hide_index=True, use_container_width=True)

    if len(result["pay_years"]) > 1:
        st.warning("Pay dates span %s. The Pay Date decides which W-2 year an "
                   "amount counts for (template rule 7), so check that every "
                   "uploaded file belongs to the year you are importing."
                   % ", ".join(str(y) for y in result["pay_years"]))

    if result["not_in_template"]:
        st.warning("**%d employee(s) have overtime but no row in the template.** "
                   "Their rows were left out — UZIO has no such employee to import "
                   "against." % len(result["not_in_template"]))
        st.dataframe(pd.DataFrame(result["not_in_template"]),
                     hide_index=True, use_container_width=True)

    if is_blocked(result):
        return
    if not result["rows"]:
        st.info("No qualified overtime found in the uploaded files.")
        return

    st.markdown("### Rows to be written")
    st.dataframe(pd.DataFrame(result["rows"], columns=TEMPLATE_HEADERS),
                 hide_index=True, use_container_width=True)

    # st.download_button reruns the script, so the bytes are built here (outside
    # any button block) and the widget simply serves them.
    st.download_button(
        "⬇️ Download filled template",
        data=fill_qot_template(tpl_file, result["rows"]),
        file_name=output_filename(client_name, tpl_file),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        key="qot_dl",
    )
```

- [ ] **Step 2: Wire it into the router**

In `app.py`, add to the ADP tool list (after `"ADP - Time Off Tool",`):

```python
            "ADP - Qualified Overtime Wages",
```

and add a routing branch next to the other ADP branches:

```python
elif tool_option == "ADP - Qualified Overtime Wages":
    from apps.adp import qualified_overtime
    importlib.reload(qualified_overtime)
    qualified_overtime.render_ui()
```

- [ ] **Step 3: Compile and confirm the module imports**

```bash
py -m compileall -q apps/adp/qualified_overtime.py app.py
py -c "import sys; sys.path.insert(0,'.'); import apps.adp.qualified_overtime as m; print('ok', callable(m.render_ui))"
```

Expected: no compile output, then `ok True`.

- [ ] **Step 4: Run the app and exercise it**

```bash
py -m streamlit run app.py --server.headless true
```

Open `ADP - Qualified Overtime Wages`, upload CDC's three payroll files and the template, set Client Name to `CDC`, and confirm:
- counters read **289 / 117 / 13589.77 / 177**
- no red blocking boxes
- the preview table's first row is `11M4UJ5DM`
- the download is named `CDC_Qualified_Overtime_Template_2026_filled.xlsx`
- opening it shows `Instructions` + `QOT Details`, 289 data rows, no blank rows

- [ ] **Step 5: Re-run all four verification scripts together**

```bash
py scratch/verify_qot_read.py && py scratch/verify_qot_template.py && py scratch/verify_qot_rows.py && py scratch/verify_qot_workbook.py
```

Expected: four `PASS` lines.

- [ ] **Step 6: Commit**

```bash
git add apps/adp/qualified_overtime.py app.py
git commit -m "feat(adp-qot): add the Qualified Overtime Wages tool to the sidebar"
```

- [ ] **Step 7: Report the mirror gap**

`apps/adp/qualified_overtime.py` and `app.py` both changed, so `implementors_repo/` needs the same files. That folder is an empty stub on this machine, so say so explicitly rather than leaving it silently unmirrored — it has to happen from Shobhit's machine.

Do **not** push. Report the branch state and wait.
