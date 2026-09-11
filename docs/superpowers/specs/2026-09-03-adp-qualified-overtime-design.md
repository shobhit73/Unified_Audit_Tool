# ADP — Qualified Overtime Wages

**Date:** 2026-09-03
**Status:** Approved for implementation
**Scope:** new `apps/adp/qualified_overtime.py` + one sidebar entry and routing branch in `app.py`. ADP only.

## Problem

UZIO's Qualified Overtime import template arrives pre-filled with one row per employee and four empty columns: Period Start Date, Period End Date, Pay Date, QOT Premium. Filling them by hand means reading the qualified-overtime memo out of every prior payroll file, per employee, per pay period. This module does that.

## Inputs

1. **Prior payroll files** — multiple, `.csv` / `.xls` / `.xlsx`.
2. **UZIO Qualified Overtime template** — single `.xlsx`.

## The template

Sheet `QOT Details`, headers on **row 1**:

```
Employee ID | First Name | Last Name | Employment Status | Period Start Date | Period End Date | Pay Date | QOT Premium
```

A second `Instructions` sheet carries 14 rules. Three of them drive this design:

- **Rule 5** — dates are optional, but a row must have **all three or none**.
- **Rule 9** — a dated row may cover a single payroll or a longer stretch; rows for the same employee **must not overlap**.
- **Rule 12** — a row **without** dates is the employee's cumulative total for the tax year, and importing it **replaces everything** previously imported for that employee.

Rule 4 says only Employee ID is read on import; name and status are ignored.

## Field mapping

| Template column | Prior payroll column |
|---|---|
| Period Start Date | `PERIOD BEGINNING DATE` |
| Period End Date | `PERIOD ENDING DATE` |
| Pay Date | `PAY DATE` |
| QOT Premium | `MEMO : $R-FDQOT` |

Employee ID matches `ASSOCIATE ID`. First Name / Last Name / Employment Status are copied from the template row for the same Employee ID — UZIO ignores them, but they keep the file readable for whoever checks it.

Dates are written **verbatim from the source** in `MM/DD/YYYY`.

## Row model

**One output row per (employee, pay date), kept only when QOT Premium is non-zero.**

The filter is per row, not per employee: an employee keeps every pay period that has a premium, and disappears entirely only when all of their rows are zero or blank. Rule 14 ("omission does not delete") makes dropping the zero rows safe.

Non-zero means non-zero in either direction — a negative premium is kept, not filtered out. Blank and `0` are both treated as "no qualified overtime" and dropped. CDC has no negatives (range 0.23 – 411.24) and 1403 of its 1692 rows carry a blank rather than a zero.

The same (employee, pay date) appearing in two uploaded files produces two rows with identical periods, which the overlap rule below treats as overlapping and therefore blocks. That is deliberate: the tool cannot know which copy is authoritative, and silently picking one would be a guess. CDC has none.

The template's pre-filled rows are **not** carried through. Left in place they would be dateless rows with a blank premium, and Rule 12 makes a dateless row a cumulative total that replaces everything already imported for that employee — a silent wipe. Only the rows this tool fills are written.

On CDC: 1692 payroll rows → **289 rows across 117 employees, 13,589.77 total**; 177 employees drop out because every one of their rows is zero or blank.

Period lengths may differ between uploaded files and that is fine — Rule 9 allows both. CDC's weekly file yields 7-day periods and its two quarterly files yield 91-day periods.

## Resolving the QOT column

Look for `MEMO : $R-FDQOT` in each uploaded file.

- Found in every file → use it, no prompt.
- Found in **no** file → show a `selectbox` listing every `MEMO`-prefixed column across all uploads; the chosen name applies to all files.
- Found in some files but not others → use it where present; skip the others and name them on screen.

## Validation

**Blocking — no file is produced:**

1. **Overlapping periods for one employee** (Rule 9). UZIO rejects the import, so producing the file would waste a round trip. The screen lists the employee, both periods and the file each came from.
2. **A row missing one or two of the three dates** (Rule 5).
3. **Template unreadable** — no `QOT Details` sheet, or its expected headers are absent on row 1.

**Reported, file still produced:**

- Employees with a premium in the payroll but **no row in the template** — their rows are left out, because UZIO has no such employee to import against. Listed with ID and amount.
- Uploaded files with no QOT column — skipped, named on screen.
- Pay dates spanning more than one calendar year — a reminder of Rule 7 (the Pay Date decides the W-2 year). Not blocking: a period may legitimately fall in an earlier year than its pay date.

## UI

Two uploaders (multi prior payroll, single template) plus Client Name, matching the layout of the other ADP tools. After the run: counters for rows emitted, employees, total QOT, and employees dropped as zero; then the mapped-rows preview, the skipped-employees table, and — when blocking — the overlap table in red.

The generated file is held in `st.session_state`, keyed by a signature of the uploaded files, and the download button renders outside the run block. `st.download_button` triggers its own rerun, which otherwise erases a result computed inside `if st.button(...)` — the same defect fixed in the Time Off tool.

## Output

`<Client>_<uploaded template's filename>_filled.xlsx` — e.g. `CDC_Qualified_Overtime_Template_2026_filled.xlsx`.

Written through openpyxl on a copy of the uploaded template so the `Instructions` sheet and all formatting survive. Within `QOT Details`, the pre-filled rows are cleared and replaced by the filled rows.

## Out of scope

- Paycom. Its prior payroll export uses different column names and would need its own mapping.
- Computing the premium. `MEMO : $R-FDQOT` is taken as the qualified overtime premium as ADP reported it; this module does no FLSA arithmetic.
- Editing or reconciling what UZIO already holds. The tool produces an import file; it does not audit one.
