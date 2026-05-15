# Changelog

All notable changes to the **Unified HR Audit Platform** will be documented in this file.

## [2026-05-15] - Status & FLSA Standardization

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
