# Changelog

All notable changes to the **Unified HR Audit Platform** will be documented in this file.

## [2026-08-17] - ADP Setup Helper: Pre/Post-Tax Classifier Hardened Against Subset-Sum Ambiguity

### Fixed
- **False pre-tax verdicts from subset-sum coincidences** (`classify_deductions_pretax`): with small weekly amounts, multiple deduction subsets can sum to the same taxable-wage gap — the old rule credited *every member of any matching subset* and locked pre-tax from *one* row, so coincidence combos flagged post-tax deductions as pre-tax (FlashHUB July file: ROTH, ACC-Accidental D&D, and CIL-Critical Illness all wrongly Pre-tax — e.g. `ROTH 23.01 + CIL 4.38 + MED 68.36 + STD 8.77 = 104.52` matched a 104.50 gap within tolerance while the true `DEN + 401K + MED = 104.50` sat right next to it). Three new rules, all verified on FlashHUB (July, Q2, and multi-file uploads — 36/36 verdicts correct, section-125 and 401k signatures intact):
    1. **Exact-first**: zero-deviation subsets discard 2-cent-tolerance subsets for that row.
    2. **Requiredness**: a row is pre-tax evidence only for deductions present in EVERY kept subset (no explanation exists without them); absent-from-all is post-tax evidence; in-some is ambiguous and votes for nothing.
    3. **Multi-row, multi-employee verification**: pre-tax needs ≥ 5 required-rows spanning ≥ 2 distinct employees, outnumbering excluded-rows (files with < 5 testable rows fall back to ≥ 2 rows; a single clean row counts only when it is the deduction's only testable row; the 2-employee bar relaxes only when a single employee ever pays the deduction). All uploaded files are concatenated before classification, so multi-file uploads widen the evidence base automatically.

## [2026-08-08] - ADP Setup Helper: FLSA Bonus Classifier Rewritten (Blended-Rate, Per-Bonus)

### Changed
- **Dual-prediction blended-rate math** (`classify_bonus`): for every testable paycheck the tool now computes BOTH possible OT amounts — discretionary (plain `1.5 × regular rate × OT hours`) and non-discretionary (FLSA blended: `Blended = (Regular Rate × Worked Hours + Bonus) ÷ Worked Hours`, `OT = (Blended/2 + Regular Rate) × OT hours`) — and the row's verdict is whichever prediction the actual OVERTIME EARNINGS matches within 1%. Matches neither / predictions indistinguishable → row is "unclear" and isn't evidence. **Worked Hours = Regular + Overtime + Double Overtime + Training** (PTO and Station Closure hours are paid-not-worked and excluded).
- **Per-bonus verdicts**: every bonus column now gets its own verdict two ways — *individual* (paychecks where only that bonus appears) and *combined* (tested with the sum of all bonuses, matching how ADP computes the rate). Agree → confirmed; disagree → `needs_review` (never guessed); one side untestable → the other side's verdict, noted. New bonus columns are picked up automatically (name contains BONUS / BN* code). Shown as a table in the UI, in the Setup Helper xlsx (Tab 2), and used to pre-fill the "Is the earning Non-Discretionary?" toggles.
- **Aggregated rows are excluded ROW-BY-ROW, not file-by-file**: uploads may mix consolidated and per-pay-period files (they get concatenated), so a file-level check would let quarter rows slip in as evidence. Each row's own `PERIOD BEGINNING/ENDING` span decides: span > 35 days → aggregated row → never evidence (skipped-count reported); span ≤ 35 days → genuine pay-period row → testable. A single-pay-period file (1 row/employee, ~7-day span) therefore classifies normally; a purely consolidated upload returns indeterminate with an explicit "upload the per-pay-period file" message — on a quarter row the bonus may sit in a pay period with no overtime (and vice versa), so aggregate math would produce a false verdict in either direction.

## [2026-08-08] - ADP Tools: Grand-Total Row Detector Hardened (Both Audit + Sanity)

### Fixed
- **Grand-total detector silently deleted a real employee row** (First Line Logistics: KZL3QQJ3T's 06/26 stub — $348 Training + 8 tax amounts vanished from the ADP side, producing 10 false mismatch rows and a false pay-stub-count diff). The old heuristic dropped the last row when ANY of the first 5 columns matched the previous row (period dates always match in per-pay-period files) and ONE money column was within a loose 5% of the sum of preceding rows — trivially coincidental in small files. Both `total_comparison.find_header_and_data` and `prior_payroll_sanity.detect_grand_total_row` now require ALL of:
    1. ≥ 3 data rows (a "sum" over one preceding row is meaningless);
    2. the true ADP totals-row signature — the last row's employee ID **equals** the previous row's (leaked identity);
    3. ≥ 3 money columns each equal to the sum of all preceding rows (GROSS PAY / TOTAL EARNINGS mirror each other, so two is one signal);
    4. 0.5% tolerance (real totals are exact sums ± cent rounding), with at least one matched column > $100.
    Verified: genuine totals rows still detected (old and new agree), the KZL false positive is gone, and full old-vs-new audit regression on First Line shows exactly the 9 falsely-suppressed items recovering — everything else byte-identical.

## [2026-08-07] - ADP Prior Payroll Sanity: Fix TypeError on Deployed (Arrow-backed pandas)

### Fixed
- **Lived-in split crashed with a redacted TypeError on Streamlit Cloud** (`split_lived_in_column`): the new per-jurisdiction column was created from `""` (string dtype) and then float money values were written cell-by-cell with `df.at[...]` — modern pandas with Arrow-backed string columns (Python 3.13 cloud env) raises `TypeError` on that; older local pandas silently allowed it, which is why it never reproduced locally. Both `split_lived_in_column` and `split_memo_column` now build whole columns and assign them once with explicit `object` dtype — version-proof across numpy- and Arrow-backed pandas. Verified against the exact crashing client files and under warnings-as-errors strict mode.

## [2026-08-07] - ADP Prior Payroll Audit: Parenthesized Columns No Longer Collide

### Fixed
- **`LIVED-IN STATE (IL)` and `(WI)` columns collided in the audit** (`total_comparison.py`): column matching used `norm_colname`, which strips everything in parentheses (a census-era rule for suffixes like `(Personal Profile)`) — so both per-jurisdiction lived-in columns normalized to the same key, the last one won, and the IL mapping row silently summed the WI column's money. `calculate_totals` now tries an **exact parens-preserving match first** (`_norm_keep_parens`) and only falls back to the paren-stripping norm; the same order applies to top-header (UZIO section) matching.

## [2026-08-06] - ADP Prior Payroll Sanity: Consistent 2-Decimal Money Output

### Fixed
- **Mixed decimal precision in the cleaned CSV**: some values showed 2 decimals, others 5-6 (`13.30056`) or float noise (`769.339999999999`). Two causes, both fixed: (1) the `=ROUND(x, 2)` formula evaluator returned the raw inner literal without applying the rounding — it now honors the formula's digit count exactly as Excel displays it; (2) a new `normalize_money_precision()` pass runs on the final output — floats round to 2 decimals, and strings are reformatted ONLY when they are plain decimal numbers with 3+ decimal places (IDs, SSNs, dates, zips can never match). Applied after all other cleanups, before download.

## [2026-08-06] - ADP Prior Payroll Sanity: 401k/Roth Memo Split Rewritten (Deferral-Driven)

### Fixed
- **Employer-match memo split picked the wrong 401k column**: `find_retirement_columns` took the *first* column containing "401k" — on files where `28-ADP 401K FLAT$` (or a `401K LOAN` column) precedes `K-ADP 401K`, nearly every employee's match was wrongly shipped to Roth (InnovDel Dec–Mar: $211 kept vs $14,937 mis-sent to Roth; correct split is ~$13,698 vs ~$1,451). It now returns **all** 401k deferral columns and **all** Roth columns, with LOAN columns always excluded.

### Changed
- **Split logic is now deferral-driven, per row** (`split_memo_column`):
    1. 401k deferral only → entire match stays in the memo column — no split, even when match > deferral.
    2. Roth deferral only → entire match moves to the Roth column.
    3. Both, match ≤ total 401k deferral (sum of all 401k columns, e.g. `K-ADP 401K` + `28-ADP 401K FLAT$`) → entire match stays.
    4. Both, match > total 401k deferral → keep up to the 401k deferral, move only the excess.
    - Neither deferral present → match stays in the memo column and the row is flagged for review (Employee IDs listed).
- **Roth split column renamed `ROTH:<memo col>` (UPPERCASE prefix)**, e.g. `ROTH:MEMO : N` — the UZIO prior-payroll import uppercases file headers but matches mapping source names case-sensitively (`PriorPayrollServiceImpl.normalizeKey` vs `contributionMapBySourceName`), so a mixed-case `Roth:` prefix silently failed to import. Mapping CSVs must carry the uppercase name too.

## [2026-08-05] - ADP Prior Payroll Sanity: Lived-in State / Local Tax Split

### Added
- **Lived-in State / Local tax split via Tax Validation Report** (ADP Prior Payroll Sanity Check): new optional upload field for the ADP **Tax Validation Report**. When the payroll file has a `LIVED-IN STATE - EMPLOYEE TAX` and/or `LIVED-IN LOCAL - EMPLOYEE TAX` column (one column that may lump several jurisdictions — unmappable downstream), each employee's amount is moved into a per-jurisdiction column by Associate ID: `LIVED-IN STATE (WI) - EMPLOYEE TAX`, `LIVED-IN STATE (IL) - EMPLOYEE TAX`, etc. (locals use the `Lived in Local Jurisdiction Description`). The jurisdiction code sits **before** `- EMPLOYEE TAX` so the new columns still end with `EMPLOYEE TAX` and are recognized as tax columns by the Setup Helper and the audit's unmapped-column scan without any change to those tools. Rules:
    - Only jurisdictions that actually carry money get a column (inserted right after the base column, alphabetical).
    - The base column is deleted once it holds no money (everything moved, or it was empty to begin with); it is kept only while unmatched values remain in it. The `... TAXABLE` column stays combined.
    - Employees with money but missing from the report (or with a blank jurisdiction) keep their value in the base column and are flagged for review — nothing is guessed or lost.
    - Duplicate Associate IDs in the report resolve to the first non-blank jurisdiction.
    - The split runs before aggregation, so both Full Quarter and Preserve Pay Periods modes see per-jurisdiction columns.

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
