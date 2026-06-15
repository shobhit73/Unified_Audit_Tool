# Changelog

All notable changes to the **Unified HR Audit Platform** will be documented in this file.

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
