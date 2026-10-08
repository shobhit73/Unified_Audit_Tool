# ADP Deduction Sanity Check

**Date:** 2026-10-08
**Status:** Implemented; `scratch/verify_adp_deduction_sanity.py` passes on 19 real client files
**Branch:** `rohit/adp-deduction-sanity` (from `origin/main` @ `f86408e`)
**Scope:** new `apps/adp/deduction_sanity.py`, plus one sidebar entry and one route in `app.py`.

## Problem

The ADP Voluntary Deduction export goes to the onboarding API as-is. The API rejects rows the export routinely carries, so these files are cleaned by hand today. 55th & 3rd, Moses, Happy Delivery and Elite OnPoint all have "cleaned", "final" or "Active EEs" copies. The hand-cleaning removes direct-deposit lines, garnishments and earned-wage-access lines, and is never recorded.

## What the API does with the file (onboarding-service source)

- `ADPConfig.toPaycomDeductionRecord` reads **only** `ASSOCIATE ID`, `DEDUCTION CODE`, `DEDUCTION DESCRIPTION`, `DEDUCTION AMOUNT` and `DEDUCTION %`, by header name.
- `EmployeeDeductionSetUpServiceImpl` looks up the mapping by **`DEDUCTION DESCRIPTION`, exactly** (`mappingBySourceName.get(desc)`). A stray space gives `No mapping found…`.
- `EmployeeDeductionValidator`:
  - the code and the description are mandatory;
  - **exactly one** of amount and percent may be filled;
  - the amount must be ≥ 0 and the percent must be in 0–100;
  - each must parse as `BigDecimal` once commas are removed, so `$` and `%` signs fail.
- An Associate ID unknown to UZIO fails every row of that employee (`Employee code not found for external ID`). A garnishment-type deduction fails with `Company deduction not found… Might be of garnishment type`.

## Decisions (Rohit)

| # | Decision |
|---|---|
| 1 | Input is **the ADP file only**: no census, no mapping file |
| 2 | One checkbox per distinct description. Direct deposit, garnishments, and Payactiv / ZayZoon / REIMBURSEMENT / Tapcheck start ticked |
| 3 | Duplicates are **flagged only**, never removed, both identical and different-amount |
| 4 | Output is a corrected CSV with **all original columns**, from which **only rows are removed**, plus an xlsx report |
| 5 | **No value is ever changed.** Whitespace, `$` / `%` signs and amount-and-% are flagged, not fixed |

## Behaviour

### Reading
- `.xlsx`, `.xls` or `.csv` is accepted. The header is the first row (within 20) that carries both `DEDUCTION CODE` and `DEDUCTION DESCRIPTION`. Preamble rows above it are dropped, and that is recorded in the Change Log because the API expects the header on row 1.
- Values are kept as text exactly as written. A CSV that is not UTF-8 is read as cp1252.
- If any of the five API columns is missing, the run **stops**: a red box names the column, and no file is produced. Happy Delivery and `Cat 5_Voluntary Deduction.xlsx` have no `ASSOCIATE ID`.

### Rows removed
1. **Always:** rows with a blank Associate ID. The `Report Totals:` line is labelled as such.
2. **Ticked descriptions.** The list shows each distinct description exactly as written, with its code(s), row count and employee count. These start ticked:

| Category | Rule (case and `%` ignored) | Seen as |
|---|---|---|
| Direct deposit | the whole description is `CHECKING` or `SAVINGS` (so `HSA SAVINGS` is **not** ticked) | CHECKING, SAVINGS |
| Garnishment | word `SUPPORT`, `LEVY` or `SPT`; a word starting `GARNISH` or `BANKRUPT`; or `WAGEAGREMNT` | SUPPORT, GARNISHMENT(%), TAX LEVY(%), BANKRUPTCY (code 70), SPT/WAGEAGREMNT (codes 75/76) |
| Earned-wage access / reimbursement | contains `PAYACTIV`, `ZAYZOON`, `TAPCHECK` or `REIMB` | Payactiv, ZayZoon DirDep, ZayZoonDirDep, TapCheck, REIMBURSEMENT, MILEAGE REIMB |

BANKRUPTCY, SPT/WAGEAGREMNT and MILEAGE REIMB were added after reviewing the real files: they are the same kinds Rohit listed, and MILEAGE REIMB carries negative amounts the API rejects.

### Flagged (nothing changed)
Flags apply to rows that stay. Each flag carries the Associate IDs:
- Deduction code blank; description blank
- Extra spaces around the Associate ID, code or description
- Amount and % both blank; amount and % both filled
- Amount or % not a plain number
- Amount negative; % outside 0–100
- Associate ID shaped like an SSN (`###-##-####` or nine digits)
- Duplicate: identical rows for the same employee and description
- Duplicate: same employee and description, different code or amount

### Output
- `<Client>_ADP_Deduction_Corrected.csv`: every original column with the removed rows taken out. Plain UTF-8, **no BOM**.
- `<Client>_ADP_Deduction_Sanity_<dd_mm_yyyy_HHMM>.xlsx`, with these sheets:
  - **Corrected Data**
  - **Removed Rows** (Source Row, Reason, then the row)
  - **Garnishments** (to be set up in UZIO separately)
  - **Flagged Rows** (Source Row, Issue, then the row)
  - **Change Log** (one line per removed row, plus a preamble line when there was one)

### Screen
- Three counters: rows kept, rows removed, rows flagged.
- A red "Needs your attention — nothing below was changed" box with one line per issue type, the row count and the Associate IDs; the full list is in an expander.
- An amber "Removed from the corrected file" box with a count per reason.
- Two download buttons. Results follow the checkboxes live; there is no Generate step.

## Out of scope
- Census and mapping-file checks (decision 1).
- Paycom, and `audit_fast_api` / MCP.
- `implementors_repo` mirror: from Shobhit's machine.

## Verification — `scratch/verify_adp_deduction_sanity.py`

| Group | Must hold |
|---|---|
| real (17 files) | kept + removed = source rows; CSV has no BOM, the same headers, and kept rows identical cell for cell to the source; Report Totals removed; nothing removed as a duplicate; 5 report sheets; one Change Log line per removed row |
| real | Happy Delivery and Cat 5 (no `ASSOCIATE ID`) are refused, naming the column |
| clients | default ticks for 20 real descriptions (HSA SAVINGS, 401K, medical and life lines are not ticked); Innovdel's 280 spaced descriptions are flagged and left unchanged; JDW duplicates are flagged and none removed; JM Parcel's SSN-shaped IDs (337 rows) are flagged; KDL's negative MILEAGE REIMB is removed by default, and flagged when unticked |
| moses | the rows kept equal the client's hand-cleaned file (271 = 271, Totals line aside) |
| synthetic | each API rule is flagged on its own row; preamble plus a blank line are read; `$25.00` and `150` are written back unchanged; a cp1252 CSV is read |
| ui (AppTest) | default ticks; two downloads; red box; unticking CHECKING brings its rows back; a missing column shows the red box and no downloads |
