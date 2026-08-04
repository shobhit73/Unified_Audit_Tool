# Changelog

All notable changes to the **Unified HR Audit Platform** will be documented in this file.

## [2026-08-04] - ADP Prior Payroll Audit: Unmapped-Money Detection (Two Tiers)

### Fixed
- **Silent skip of incomplete mapping rows** (ADP Prior Payroll Audit / `total_comparison.py`): a mapping row with the source name filled but the UZIO side blank (e.g. `HOPEWELL TWP,`) was silently dropped while loading, so any ADP money under that column vanished from the audit entirely — no mismatch, no warning. **Tier 1:** such rows are now collected separately; when the ADP file(s) carry money under them, real mismatch rows are emitted (`ADP amount` vs `0`, item suffixed **`(MAPPING INCOMPLETE)`**) in Full Comparison, Mismatches Only, and Employee Mismatches, plus a UI banner listing the incomplete rows. Zero-money incomplete rows get an info notice only.

### Added
- **Tier 2 — "Unmapped Columns" review list**: ADP columns that carry money, *look* mappable (`… - EMPLOYEE/EMPLOYER TAX`, `ADDITIONAL EARNINGS : …`, `VOLUNTARY DEDUCTION : …`, `REGULAR/OVERTIME EARNINGS`), and appear in **no** mapping file are listed informationally (UI expander + new `Unmapped Columns` report tab) — never as mismatch rows. Structural columns (`TAXABLE` wage bases, `TOTAL*`, `HOURS`, `MEMO`, `DIRECT DEPOSIT`, `GROSS`, `NET PAY`, `TAKE HOME`) are excluded by design and can never be flagged.

## [2026-07-31] - Prior Payroll Setup Helper: 401k Loan Mapping + % of Gross for Deferrals

### Fixed
- **ADP Setup Helper — "401K LOAN1" mis-mapped to `401k`**: the word-boundary keyword matcher rejected `401k loan` inside descriptions like `ADP 401K LOAN1` because of the trailing sequence digit, then fell through to the bare `401k` keyword. Trailing digits are now allowed after a keyword (`LOAN1`, `SUPPORT2`), so 401k loans map to the `401(k) Loan` master (which keeps Method `Fixed $`). Letters still break the match (`dental` ⊄ `accidental`).

### Changed
- **Both Setup Helpers (ADP + Paycom) — 401k / Roth 401k Method**: deductions mapped to the `401k` or `Roth 401k` masters now get UZIO Method **% of Gross Pay** instead of `Fixed $` (retirement deferrals are percent-of-pay elections in UZIO). `401(k) Loan` remains `Fixed $`.

### Fixed
- **ADP Setup Helper — informational memos auto-detected as employer contributions**: the value-based match detector (small-%-of-gross + deferral co-occurrence) was pre-selecting hour-balance and wage-tracker memos (`PTO-PTO/SICK`, `BNH-BONUS HOURS`, `$R-FDQOT` Federal Qualified Overtime) as 401k matches — hour counts and OT dollars land in the same ratio band. The value path now skips memo labels containing informational keywords (`PTO`, `SICK`, `VAC`, `HOURS`, `BAL`, `DATE`, `ZONE`, `TAX`, `MAX`, `BONUS`, `OT`, `QOT`, `FDQOT`, ...). Explicit `MATCH` labels and `Roth:` split columns are never filtered. All memo columns remain available in the picker for manual selection.
- **ADP Setup Helper — duplicate contribution names**: multiple opaque memo codes falling back to the generic "401K Match" name are now suffixed with their source code (`401K Match (N)`, `401K Match (BNH)`) so UZIO never receives identically-named contributions.

## [2026-07-17] - ADP Prior Payroll Sanity: Auto-add Pay-Period Date Columns

### Added
- **Missing pay-period date columns auto-fix** (ADP Prior Payroll Sanity Check): consolidated quarter files from ADP often arrive without `PERIOD BEGINNING DATE`, `PERIOD ENDING DATE`, and `PAY DATE`, which the downstream API requires. The tool now fills them automatically, in this priority order:
    1. **Columns present** → the file is left untouched (even if some cells are blank).
    2. **Columns missing → filename dates**: the filename must contain exactly one run of three 8-digit `MMDDYYYY` blocks joined by underscores, in `<begin>_<end>_<pay>` order (e.g. `PriorPayroll_01012026_01072026_01142026.xlsx`). Each block is validated as a real calendar date. The parsed dates are shown in the UI for confirmation before running.
    3. **Filename unparseable → manual input**: three date pickers appear; the Run button refuses to proceed until all three are filled.
    - The missing columns are inserted **between `WORKED IN STATE` and `GROSS PAY`** (falling back to before `GROSS PAY`, then after `WORKED IN STATE`, then appending at the end) and stamped on every row as `MM/DD/YYYY` text — the only format the API accepts. Columns that already exist are never modified; only the missing ones are added.

## [2026-06-11] - ADP Prior Payroll Sanity: 401k / Roth Memo Split

### Added
- **401k / Roth employer-match memo split** (ADP Prior Payroll Sanity Check): when the file has `K-401K` and/or `R-Roth` deduction columns, the tool identifies the MEMO column carrying the combined employer-match money — the memo column whose entry count equals the number of employees having K-401K **or** R-Roth (a `0.00` cell counts as an entry; blanks and `-` don't).
    - **Split rule (per employee)**: memo money stays in the matched memo column up to the employee's K-401K amount; all excess moves to a new `Roth:<memo column>` column inserted immediately to its right. Employees with no K-401K value move the entire memo amount.
    - **Tie or no count match**: the tool flags it and the user picks the memo column manually (or skips the split) before running. An unambiguous match is shown for confirmation and applied on run.
    - Detection runs **after** aggregation (on the final cleaned rows), under whichever aggregation strategy is selected.

### Added
- **MCP Server Sync**: All census sanity and auto-fix rules are now fully synchronized with the `audit_fast_api` MCP server.
- **Payroll Exclusion Prompt**: Added a specific UI warning for employees on leave/inactive missing a termination date: *"Please make them excluded from payroll on Uzio"*.

### Changed
- **Employment Status Logic**: 
    - Employees with "On Leave" or "Inactive" status and **no termination date** are automatically converted to **"Active"** with a "Excluded from payroll" comment in the change log.
    - If a **termination date is present**, they are converted to **"Terminated"**.
- **FLSA Classification Rules**:
    - **Driver Rule (Forced)**: Any job title containing "Driver", "Lead Driver", "Driver Helper", etc., is now forced to **Non-Exempt**, regardless of pay type (Hourly or Salaried).
    - **Salaried Fallback**: Blank FLSA + Salaried pay type -> **Exempt**.
    - **Hourly Fallback**: Blank FLSA + Hourly pay type -> **Non-Exempt**.
- **Nomenclature Standardization**:
    - Standardized "Full-Time" to **"Full Time"** across both ADP and Paycom modules.
    - Emergency Relationship fix: Any relationship starting with **"Fian"** is automatically corrected to **"Fiancee"**.

## [2026-05-13] - Census Audit Hardening

### Added
- **Selective Census Sync Enhancements**: Improved attribute handling for existing Uzio templates.
- **Change Log Tracking**: Every automated data correction (FLSA, Status, Zip, etc.) is now explicitly logged in a "Change Log" tab and CSV output.

### Changed
- **Paycom Generator Logic**: Refined the "DSP Owner" detection and sorting priority.

## [2026-03-20] - Initial Unified Release
- Consolidation of ADP and Paycom audit modules into a single Streamlit router.
- Implementation of the "Editorial Ledger" UI design system.
