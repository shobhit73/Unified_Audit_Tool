# Paycom Time Off — bring it to ADP parity

**Date:** 2026-10-06
**Status:** Implemented; `scratch/verify_paycom_timeoff.py` passes on the real Banda files
**Branch:** `rohit/paycom-timeoff-parity` (from `origin/main` @ `ace3c1d`)
**Scope:** `apps/paycom/timeoff_audit.py` only. ADP is not touched.

## Problem

Today's Paycom tool (`ace3c1d`):

1. **Writes the wrong column.** It fills Opening Balance from `Net Available`, which Paycom computes as `Available − Future Approved − Future Pending` (exact on every Banda row). At Banda that is 108 of 640 rows, with a client total of −1,575.72 against 2,187.34 Available. ABEL, JACOB: Available 4.98, Net −48.55. The balance to import is **`Available`**.
2. **Ignores the policy.** It keys balances by employee only and writes the last Paycom row into every template row the employee has, whatever its `Time Off Policy Name`. That is the same bug the ADP tool had for Moses (prenatal leave overwritten with PTO).
3. **Has none of the ADP tool's controls.** There is no policy mapping, no Salaried or Hourly blank-fill switch, no census, and the audit tabs are written into the import file itself, so the user has to delete them before uploading.
4. Smaller defects: the name column can resolve to `Employee Code`, and a blank `Future Approved` cell crashes the run (`float(" ")`).

## Decisions (Rohit)

| # | Decision |
|---|---|
| 1 | Three uploaders, **all mandatory**: Paycom TimeOff Summary Report, UZIO Time Off Template, UZIO Census |
| 2 | Opening Balance = Paycom **`Available`**, not `Net Available` |
| 3 | Future time off is shown in its own **Future Time Off** sheet, and **not** in Exception Summary |
| 4 | Mapping, checkboxes and audit are the same as ADP |
| 5 | Implementation: **copy the ADP module and adapt it** (approach B). No shared engine, and the ADP file is not edited |

## The Paycom report (Banda, real file)

`20261002123220_TimeOff_Summary_Report_….xlsx`: one sheet, one row per employee per **Time-Off Type**, with plain numeric strings (no `=ROUND()` formulas).

| Column | Use |
|---|---|
| `EECode` | Employee ID (matches UZIO `Employee ID`, e.g. `A03K`) |
| `Employee` | Name, `LAST, FIRST` |
| `Time-Off Type` | Policy (Banda: only `Paid Time Off`) |
| `Available` | **Opening Balance** |
| `Future Approved`, `Future Pending`, `Net Available` | Future Time Off sheet only |
| `Unit of Time` | Banda: always `Hours` |
| `Department`, `Total Accrued` | not used |

## Behaviour

### 1. Upload

| Uploader | Types | Key |
|---|---|---|
| Paycom TimeOff Summary Report | xlsx, xls, html, csv (read with `read_report`) | `pt_p` |
| UZIO Time Off Template | xlsx | `pt_u` |
| UZIO Census | xlsx, xlsm, csv | `pt_c` |

Generate with any of them missing → `Please upload: <missing names>.`, and nothing runs.

### 2. Reading the Paycom report — `read_paycom_balances`

The report is read with `read_report(file, header=0, dtype=str)`. Headers are normalized the ADP way (`_norm_header`).

- **ID:** the header `eecode`, else one containing `employee code`, else `employee id`.
- **Balance:** the header that is **exactly** `available` after normalizing. A `contains` match would also catch `Net Available`.
- **Policy:** the header containing `time-off type` or `time off type`. If there is none, every row's policy is `(no policy name)`.
- **Name:** the header exactly `employee`, else one containing `employee name`.
- If the ID or `Available` column is missing, the run stops with an error that lists the columns it did find.
- IDs go through `clean_id` on both sides, the same as ADP.
- Rows are grouped by (ID, policy), and `Available` is summed with `_sum_money` (one rounding, `min_count=1`, no `-0`). Paycom gives one row per pair; the sum only guards against duplicates.
- `Future Approved`, `Future Pending` and `Net Available` are kept per (ID, policy) for the Future Time Off sheet. A blank or non-numeric cell counts as 0 and never crashes the run.
- `Unit of Time` is kept. Any row whose unit is not `Hours` produces a screen warning naming each Time-Off Type and its row count, because UZIO balances are in hours.

Returns `(DataFrame[id, policy, balance, name, future_approved, future_pending, net_available, unit], error)`.

### 3. Mapping and checkboxes — identical to ADP

- One dropdown per Paycom `Time-Off Type`, showing its employee count and total `Available`. The options are every template policy plus **Do not import**.
- Auto-map uses the same rule as ADP: a type matching `\bPTO\b` or `paid time off` goes to the template's `Paid PTO` (or its single PTO-named policy); everything else starts on Do not import. At Banda, `Paid Time Off` → `Paid PTO`.
- ☐ **Fill balances for Salaried employees too**, off by default.
- ☑ **Fill blank Opening Balance for Hourly employees (assigns the policy in UZIO)**, on by default.
- `plan_fill` and `fill_import_template` are copied unchanged: matching is by (employee, UZIO policy), several types mapped to one policy are summed, a Salaried blank row is never filled, and negative balances are written as they are (4 at Banda).
- Changing a mapping or a checkbox after Generate discards the previous result, as in ADP.

### 4. Output — two files

- `<Client>_Time off Import_filled.xlsx`: the uploaded template with only Opening Balance cells changed. It can be uploaded as-is.
- `<Client>_Uzio_Paycom_TimeOff_Audit_Report_<dd_mm_yyyy_HHMM>.xlsx`, with these sheets in order:

| Sheet | Content |
|---|---|
| Policy Mapping | ADP layout, headers `Paycom Time-Off Type`, `Mapped To`, `Employees`, `Total Paycom Available`, `Set By` |
| Balance vs UZIO Status | ADP layout. `ADP Balance` becomes `Paycom Balance`; Terminated employees are listed first |
| Unassigned Policies | as ADP |
| **Future Time Off** | one row per Paycom (employee, type) with Future Approved > 0 or Future Pending > 0. Columns: `Employee ID`, `Employee Name`, `Time-Off Type`, `Mapped To`, `Available`, `Future Approved`, `Future Pending`, `Net Available`, `Employment Status`, `Termination Date`. When there are none, it shows a single `No future time off found` message |
| Exception Summary | ADP's columns with `ADP Balance` → `Paycom Balance`. Categories as ADP, with "ADP" replaced by "Paycom": `Paycom policy not imported (<type>)`, `Terminated in UZIO but Paycom sent a balance`. **Future time off is not listed here** |

**Possible Census Match** (added after review): Balance vs UZIO Status, Future Time Off and Exception Summary carry a `Possible Census Match` column. It is filled only when the Employee ID is not in the census. It lists every census employee with the same first word of the first name and the same last word of the last name, as `A09A (TERMINATED)`, separated by `; ` when there are several. At Banda, 3 of the 11 employees missing from the census are there under a different EECode (A09S→A09A, A0H0→A0I4, A0HW→A0I5, all Terminated). A surname-only match is never suggested.

The old `Missing in Uzio` and `Paycom Raw Data` sheets are dropped. Missing employees are `In Import Template = No` in Balance vs UZIO Status, and they still count toward the Missing counter and Exception Summary (`Missing in Uzio Template`), as in ADP.

### 5. Screen

- The ADP layout carries over: 4 counters (`Employees in Paycom`, `Balances written`, `Missing in UZIO`, `Terminated in UZIO`), the "Left out on purpose" box, the blue blank-filled note, and the green or red outcome message.
- One extra line when there is future time off: `N employee(s) have future time off in Paycom — see the Future Time Off sheet.`
- The Unit-of-Time warning from §2, when it applies.
- The instructions block is rewritten to describe three uploads and two output files. The old "delete the extra tabs" note goes.

## Unchanged / out of scope

- `apps/adp/timeoff_audit.py`: not edited.
- `audit_fast_api` / the MCP `paycom_timeoff_audit` tool: not touched.
- `implementors_repo` mirror: from Shobhit's machine (the folder is empty on Rohit's).
- Mapping memory across runs.

## Verification — `scratch/verify_paycom_timeoff.py`

The real Banda files are the Paycom report, `Time Off Import.xlsx` (111 rows, all `Paid PTO`, all Opening Balance 0, 105 Hourly / 6 Salaried) and `Multi_Client_Banda Logistics LLC_Employee_Census.xlsm`. The old module is loaded from **pinned `ace3c1d`** via `git show`, not from `HEAD`.

| Case | Must hold |
|---|---|
| Column | every written cell equals that employee's Paycom `Available` for `Paid Time Off`. On the 59 matched rows where Available ≠ Net Available, new = Available while old = Net Available. This is the before/after table |
| Auto-map | `Paid Time Off` → `Paid PTO`, Set By = Auto |
| Salaried off (default) | the 6 Salaried rows stay 0; each one with a Paycom row is listed as `Salaried — not filled (Paid PTO)` |
| Salaried on | those rows are filled with Available |
| Template-only IDs | the 8 IDs with no Paycom row are untouched |
| Import file | identical to the uploaded template apart from Opening Balance cells; it has only the template's own sheets |
| Future Time Off | 108 rows (every Paycom row with future > 0, matched or not); no future category in Exception Summary |
| Status | Balance vs UZIO Status lists Terminated first; census status reaches Exception Summary |
| Synthetic: 2nd type | an added `Sick` type starts on Do not import, is never written, and appears as `Paycom policy not imported (Sick)` where non-zero |
| Synthetic: blank Hourly row | filled by default and named `Blank filled — policy assigned (Paid PTO)`; not filled with the box off |
| Synthetic: robustness | blank `Future Approved` does not crash; `Unit of Time = Days` produces the warning; a report without `Available` (only `Net Available`) is refused with the column list |
| UI (AppTest) | three uploaders; Generate with one missing names it; the mapping dropdown defaults; Salaried box unchecked, blank box checked; two download buttons; changing the mapping discards the result |
