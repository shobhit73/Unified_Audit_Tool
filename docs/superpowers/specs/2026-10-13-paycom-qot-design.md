# Paycom - Qualified Overtime Wages

**Date:** 2026-10-13
**Status:** Implemented; `scratch/verify_paycom_qot.py` passes on the real Banda files
**Branch:** `rohit/paycom-qot` (from `origin/main` @ `1b03a0a`)
**Scope:** new `apps/paycom/qualified_overtime.py`, plus one sidebar entry and one route in `app.py`. It is the ADP tool copied and adapted; the ADP module is not touched.

## Inputs (Banda, real files)

**Paycom `estimated_qualified_premiums_report`**
- One sheet with **one row per employee** and **no dates or pay periods**.
- Columns: `EE Code`, `Employee Name`, `Status`, `W-2 Box` (`[14] Other`), `W-2 Box Description` (`Qualified OT`), `Estimated Qualified Premiums`, `Source`.
- Banda: 96 employees, total $6,402.50, two of them at 0.

**UZIO `Qualified_Overtime_Template_2026.xlsx`**
- Sheet `QOT Details`: 330 pre-filled employees with blank dates and blank premium.
- Sheet `Instructions`: this template version numbers its rules 1–11. The ones that matter here:
  - **9:** a dateless row is the employee's cumulative total for the tax year, and a dateless 0 clears the employee's imported amounts.
  - **11:** an omission deletes nothing.

## Decisions (Rohit)

| # | Decision |
|---|---|
| 1 | Write only employees with a non-zero premium, and clear the template's pre-filled rows (rule 11 protects everyone left out) |
| 2 | Skip a premium of 0, because a dateless 0 would clear what is already imported |
| 3 | Write **dateless** rows; Paycom's figure is the year's total |
| 4 | Several report files may be uploaded; **the same EE Code in two files blocks** |
| 5 | **No filter on `W-2 Box Description`**: every row counts. Several rows for one employee in one file are **added into one row**, since the template takes one cumulative row per employee, and the screen lists them |
| 6 | A status difference between Paycom and the template is only a warning; UZIO reads just the Employee ID |
| 7 | An EE Code missing from the template is left out and reported |

## Behaviour
- **Required columns.** `EE Code` and `Estimated Qualified Premiums` are matched case-insensitively. A file without them is named in a warning and left out.
- **Reading the premium.** Files are read with `keep_default_na=False`, so `N/A` reaches the parser instead of becoming a silent blank. `$` and `,` are dropped, and `(12.34)` is read as −12.34. Anything else that is not a number **blocks** the run and is listed.
- **Telling uploads apart.** Uploads are distinguished by position, not name, so the same report uploaded twice is caught as a cross-file duplicate instead of being added together.
- **Output.** `<Client>_<template name>_filled.xlsx`. The pre-filled rows are cleared, and one row per employee is written with Employee ID, First/Last Name and Employment Status from the template, **empty** dates and a numeric QOT Premium. The Instructions sheet and formatting are kept.
- **Screen.**
  - Counters: rows to import, employees in Paycom, total QOT, and rows skipped at 0.
  - A red block, with no download, for non-numeric premiums or cross-file duplicates.
  - An info table for combined rows, and warnings for employees missing from the template and for status mismatches.
  - A preview of the rows to be written, then the download.

## Verification — `scratch/verify_paycom_qot.py`

| Group | Must hold |
|---|---|
| banda | 94 rows (96 − 2 zero); total $6,402.50, equal to the report; every premium equal to Paycom's; all dateless; A0DX / A0JK status mismatches reported; sheets and Instructions unchanged; QOT Details holds exactly the 94 rows; file total $6,402.50; output name |
| synthetic | `parse_premium` cases; two rows for one employee add up (3.06 + 10.00 = 13.06) and are reported with both descriptions; `(2.00)` → −2.00; the same EE Code in two files blocks, naming both; `N/A` blocks; an unknown EE Code is reported; a report without the premium column is refused; CSV gives the same rows as xlsx |
| ui (AppTest) | metrics 94 / 96 / 6402.50 / 2; status warning; one download; the same report uploaded twice is blocked with no download |

Two bugs were caught by these checks before shipping:
- `N/A` was turned into a blank by pandas and skipped silently.
- Two uploads with the same file name were added together instead of blocked.
