# Changelog

All notable changes to the **Unified HR Audit Platform** will be documented in this file.

## [2026-08-20] - ADP Setup Helper: Learned Earning Codes No Longer Overwrite Good Names

### Fixed
- **A truncated ADP column header silently destroyed a correct catalog entry.** ADP truncates its column labels — `PTO-PAID TIME OFF` arrives as `PTO-PAID TIME O`, `NUR-NURSERY ROUTE` as `NUR-NURSERY ROU` — and `save_learned_earning_codes` merged with `{**existing, **new_codes}`, so the learned (truncated) value won unconditionally. Running the tool on such a file rewrote the tracked `apps/adp/adp_earning_code_catalog.json`, replacing `"PTO": "Paid Time Off"` with `"Paid Time O"`. The catalog is the fallback that names **code-only** columns (`ADDITIONAL EARNINGS : LK2`), so a corrupted entry could later surface as a real UZIO Earning Name — for a different client, since the catalog is shared.
- `_better_earning_name()` now decides: when one value is a **prefix** of the other the longer one wins (a prefix is a truncation, never an update); a genuine disagreement (`Holiday` vs `Vacation`) keeps the stored value rather than silently flipping. This is self-healing in both directions — a later full-length file repairs an already-truncated entry — and removes the dependence on the order files happen to be analysed in, which previously decided the answer:
    - before: `PAID TIME OFF` then `PAID TIME O` → `Paid Time O`; reversed → `Paid Time Off`
    - after: either order → `Paid Time Off`
- Learning happens in `adp_earnings_to_setup_rows()` (called while the Earning Setup section renders), not during the analysis itself, so it fires during ordinary UI use — which is how the corruption reached the working tree three times in one session.

### Added
- `save_learned_earning_codes()` returns `{"added": ..., "improved": ...}` and the Earning Setup section shows an info box when this run changed the catalog, naming the codes. `adp_earning_code_catalog.json` is tracked in git but written at runtime, so an analysis leaves the working tree dirty; now that learned values can no longer degrade good ones, whatever lands there is genuinely new and the user is told to commit it instead of finding it in `git status`.

### Notes
- **No existing output changes.** When a column header carries a description, that description always wins and the catalog is not consulted — verified by running the same file against a good, a corrupted and an empty catalog and getting identical rows. The catalog only decides code-only columns, and codes in `ADP_EARNING_CODE_SEEDS` outrank it either way. Regression across two real client files: setup rows and `Earnings_mapping.csv` byte-identical old vs new.
- The committed catalog was never corrupted (`"PTO": "Paid Time Off"` is intact in git) — the damage was caught in the working tree each time.
- A code seen for the **first** time with a truncated header still enters truncated; the rule cannot invent missing letters. It can be healed by a later full-length file, and the new info box surfaces it for manual correction before committing.

## [2026-08-20] - ADP Setup Helper: Employee Deduction Mapping File (5th Mapping CSV)

### Added
- **`<Client>_EE_Deductions_mapping.csv`** — the mapping file the onboarding API needs for the *employee deduction assignment* call, which until now was built by hand. A new **optional** upload ("ADP Voluntary Deduction export") sits beside the Prior Payroll uploader; when present, a fifth CSV joins the existing download bundle. With no upload, every existing output is unchanged.
- It cannot reuse `_Deductions_mapping.csv`: that file's source name is the prior payroll **column header** (`VOLUNTARY DEDUCTION : LTD-LTD POST TAX`), while `EmployeeDeductionSetUpServiceImpl` looks up `mappingBySourceName.get(csvRecord.getDeductionDesc())`, which `ADPConfig.toPaycomDeductionRecord()` fills from the export's `DEDUCTION DESCRIPTION` (`LTD Post Tax`). That lookup is a plain `HashMap.get` — **case-sensitive and untrimmed** — so source names are copied VERBATIM from the uploaded file. (The Uzio side is matched `.trim().toLowerCase()`, so only the source side is fragile; same failure mode as the `ROTH:MEMO : N` uppercase bug.)
- **Join is code + base master, not code alone.** The export carries `88-ADP 401K%` / `87-ADP ROTH%` while the prior payroll carries `K1-ADP 401K` / `6-ADP ROTH`. Both sides resolve to the `401k` / `Roth 401k` base (`_base_master()` drops the ` Pre-tax` / ` After-tax` suffix), so they join with no alias table. A client running both a percent and a flat-dollar 401k gets one row per description, both pointing at the same Uzio deduction.
- **UZIO names are copied from `enriched_deds`, never recomputed** — re-running the mapper would discard the empirical Pre/Post-tax verdict and the user's Master-override and rename, none of which the export carries (the API sets `taxTreatment(null)`). Membership in `enriched_deds` / `skipped_deds` is also what "was this in the prior payroll?" means. Verified: renaming `K1` in the UI flows through to the `88-ADP 401K%` row.
- **Excluded** (never assigned to employees during onboarding): deductions resolving to Child Support / Spousal Support Order / Creditor Garnishment / Federal or State Tax Lien — which covers Support, Garnishment (`73`, `93-GARNISHMENT%`) and Tax Levy — plus descriptions matching `CHECKING` / `SAVINGS`, which are direct deposits riding in the same export. Listed on screen, not silently dropped.
- **Unresolved rows are left out of the CSV and reported in red.** A description matching neither by code nor base master was not in the prior payroll, so the deduction does not exist in UZIO. Emitting a best-effort master was rejected because it can *succeed with the wrong answer*: with no verdict available the mapper defaults to a paired family's Pre-tax variant, so a coin-flip `Critical Illness Pre-tax` would silently assign the wrong tax variant to every employee if that master happened to exist.
- Two codes sharing one description collapse to a single row (the API keeps whichever it reads first via `Collectors.toMap(..., (first, second) -> first)`); when they resolve to different Uzio names an amber warning names both.
- Reading is content-driven: the workbook ships a second `Report Runtime Settings` sheet and the data sheet name varies by client, so the first sheet carrying both `DEDUCTION CODE` and `DEDUCTION DESCRIPTION` wins. Rows with a blank ID/code/description are dropped, which removes ADP's `Report Totals:` footer without pattern-matching it.

### Verification
- On the real High Distinction files (338 rows -> 337 after the totals row, 118 employees) the generated CSV is **byte-identical** to the hand-built sample, including row order (first appearance in the file): 12 mapped, 5 distinct descriptions excluded, 0 unresolved, 0 conflicts, no BOM.
- Regression, old module vs new: `run_setup_helper` output, `enrich_deductions_for_uzio`, `enrich_earnings_for_uzio`, `Deductions_mapping.csv` and `Earnings_mapping.csv` all identical; every sheet of `UZIO_Setup.xlsx` identical (the 1-byte size delta is a zip timestamp). The diff is 270 additions and one reworded comment.
- Edge cases covered: rename propagation through the base-master join, unresolved rows, all six exclusion paths, conflicting duplicate descriptions, `skipped_deds` honoured (`PAC-PAYACTIV` -> `Earned Wage Access`), missing-column error, and totals-row removal.

### Notes
- ADP only. Paycom's equivalent export is a different shape and is untouched.
- Design: `docs/superpowers/specs/2026-08-20-adp-ee-deduction-mapping-design.md`.
- `LTD Post Tax` -> `Voluntary LTD After-tax` depends on the LTD code seed added 2026-08-19.

## [2026-08-19] - Setup Helpers (ADP + Paycom): LTD Deductions Now Map to Voluntary LTD After-tax

### Fixed
- **`LTD` deductions fell through to `<NEEDS REVIEW>`** even though `Voluntary LTD After-tax` has always been in the UZIO Master Deductions List. `LTD` was absent from the code seeds and from every keyword list, so `VOLUNTARY DEDUCTION : LTD-LTD POST TAX` produced no master, kept the raw description as the Deduction Name, and — because `BENEFIT_TYPE_KEYWORDS` had `voluntary std` but not `voluntary ltd` — was not treated as a benefit type: `Auto-Sync = N/A` (no toggle in the UI), `Track arrears = No`, blank `Arrears Processing Method`, `W-2 Box = Not Required`. LTD is a benefit exactly like STD. Added `"LTD": "Voluntary LTD After-tax"` to the code seeds (a plain string, not a Pre/After-tax tuple — UZIO ships no `Voluntary LTD Pre-tax`, same as STD) and `"voluntary ltd"` to `BENEFIT_TYPE_KEYWORDS`. LTD rows now come out byte-identical to STD apart from the master name: `Fixed $`, `Track arrears = Yes`, `Arrears Processing = Total Amount`, W-2 Box locked, and a working Auto-Sync toggle (default Off, Select All covers it). Applied to both `apps/adp/` and `apps/paycom/`, whose Auto-Sync captions now list LTD alongside STD.
- Deliberately scoped to the **code seed only** — no `ltd` / `long term disability` keyword was added, matching how STD works today. A description-only file (`73-LONG TERM DISABILITY` with a numeric code) still needs review, exactly as `73-SHORT TERM DISABILITY` would. A bare `ltd` keyword was rejected outright: it would collide with company names such as `ABC LTD-GARNISHMENT`.

### Verification
- A/B over the pre-change module across every code seed and keyword: **ADP 186 (label x tax) probes, 9 changed — all `LTD`**; **Paycom 63 probes, 6 changed — all `LTD`**. `81-LTD`, `ABC LTD-GARNISHMENT` and `('', 'LTD')` are unchanged on both sides, confirming no keyword collision was introduced.

## [2026-08-18] - ADP Withholding Audit: Every Employee Reported ACTIVE; W-4 History Over-Flagged

### Fixed
- **Every employee was labelled ACTIVE, so terminated employees landed in the "act on first" sheet** (`parse_uzio`): the status column was resolved by the single literal `UZIO_STATUS_COL = "status"`, but UZIO's current withholding export names it `employment_status`. The lookup missed, `status_by_emp` came back empty, no ADP column matched the status-like fallback scan, and every employee fell through to `status = "ACTIVE"  # safe default`. On High Distinction (376 employees, **273 of them TERMINATED**) the report claimed `Active 5 / Terminated 0` when the truth was `Active 0 / Terminated 5` — all three flagged employees were ex-employees, `Mismatches (Terminated)` was empty, all 405 Stale UZIO rows were stamped ACTIVE (really 243 TERMINATED / 162 ACTIVE), and `Missing in ADP` showed a blank status. Now resolved via `_find_col(df.columns, UZIO_STATUS_CANDIDATES)`, which accepts `employment_status`, `status`, `employee_status`. This was a UZIO export-format change: older extracts (Innovdel, First Line Logistics) ship `status` and were never affected — both column names now work, verified byte-identical on those two files.
- **"Has W-4 History" / "Verify In UI First" flagged employees with no W-4 revision** (`parse_adp`): `multi_ids` came from `groupby(id_col).size()` — a **row** count. ADP emits an extra row per state tax jurisdiction, so multi-state employees and rows differing only in `Lived In State Tax Code` were read as W-4 revisions. High Distinction reported 75 employees with W-4 history when only **3** have more than one distinct `Federal/W4 Effective Date` (the other 72 differ solely in `Lived In State Tax Code`, a column the audit does not even read); Innovdel reported 38 vs a true 3, putting a spurious "confirm the latest W-4 in the UZIO UI before changing" on 19 mismatch rows. Now counts distinct W-4 effective dates (`nunique(dropna=True)`, which flags nobody when no date parses rather than everybody). `multi_ids` is computed *after* the dedup and only ever fills two display columns, so no comparison, category, stale, reciprocity or false-positive result moves — confirmed by an old-vs-new run across all three client files: **finding identity lost=0 gained=0** everywhere, with only `EMPLOYMENT_STATUS`/`STATUS`/`HAS_W4_HISTORY`/`VERIFY_IN_UI_FIRST` and the summary metrics differing.

### Changed
- Summary metric renamed *"Employees with W-4 history (multiple ADP rows)"* → *"(multiple W-4 effective dates)"*, and the UI tile *"ADP rows w/ W-4 history"* → *"ADP rows deduped away"*, since it counts rows dropped by dedup — which are not all superseded W-4s.

### Known issue (not addressed here)
- **Multi-state employees: only the worked state is audited, and the row picked is order-dependent.** `sit_states` takes just `Worked in State Code` from the single deduped row, so an employee with two `State Tax Code` rows (Innovdel: 36 employees on IA+IL / IA+WI reciprocity pairs) never has the second state compared. Worse, 32 of those employees differ between rows in the compared SIT columns, and the dedup tie-break is arbitrary: reshuffling the input rows of the same file yields 486 / 488 / 491 mismatches with findings flipping between `Mismatch` and `Blank vs Value`. High Distinction and First Line Logistics are unaffected (0 multi-state rows, 0 order sensitivity). Tracked separately.

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
