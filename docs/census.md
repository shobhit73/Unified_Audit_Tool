# Census Audit Tools - Technical Documentation

This guide provides a detailed overview of the Census Audit tools (ADP and Paycom) to assist developers and AI agents in understanding the architecture and logic before implementing enhancements.

## 1. Core Objectives
The tools are designed to perform a "sanity check" between **Uzio** (Benefit Platform) and **Source Systems** (ADP/Paycom). The goal is to ensure data integrity across both platforms, particularly for sensitive compliance fields like FLSA status and Pay Types.

---

## 2. Architecture & Data Flow

### A. Source File Extraction
**File**: [employee_extractor.py](file:///c:/Users/shobhit.sharma/Downloads/Deduction%20Tool/apps/common/employee_extractor.py)
The extractor handles diverse Excel and CSV formats. It does not rely on filenames; instead, it "peeks" at the internal sheet names and column headers to identify the source.
- **Detection Logic**: If a file contains "Associate ID", it's treated as an ADP Export. If it has an "Employee Details" sheet, it's treated as a Uzio Census.
- **Extended Support**: Includes support for Uzio Multi-Client templates and ADP Emergency & License reports.

### B. The Normalization Engine
**File**: [audit_utils.py](file:///c:/Users/shobhit.sharma/Downloads/Deduction%20Tool/utils/audit_utils.py)
This utility file contains the shared logic for standardizing data before comparison.
- **Employee ID (`norm_id`)**: Strips leading zeros and standardizes to strings. This is the primary join key.
- **Identity Correlation (`get_identity_match_map`)**: A critical feature that links employees who have **different IDs** in different systems but share the **same SSN**.
- **Date Standardization (`try_parse_date`)**: Converts all dates to `MM/DD/YYYY` strings for equality checks.

### C. System-Specific Audits
**Files**: [adp/census_audit.py](file:///c:/Users/shobhit.sharma/Downloads/Deduction%20Tool/apps/adp/census_audit.py) & [paycom/census_audit.py](file:///c:/Users/shobhit.sharma/Downloads/Deduction%20Tool/apps/paycom/census_audit.py)
These files coordinate the audit process. They define internal mappings (e.g., Uzio 'Job Title' -> ADP 'Job Title Description') and run the comparison loops.

---

## 3. The Audit Report (Excel Tabs)

### 1. Comparison Detail
The row-by-row mismatch report. It compares every field defined in the system mapping.
- **Data Match Logic**: Uses normalized comparison (e.g., Hourly vs hourly = Match).

### 2. ID Correlation (Identity Match)
Highlights employees matched via SSN who have inconsistent Employee IDs across platforms. This is vital for cleaning up payroll-system discrepancies.

### 3. Salaried Driver Exceptions
A safety check for logistics clients. It flags any "Driver" job title assigned a "Salaried" pay type, as this often breaks benefit auto-sync systems.

### 4. FLSA Compliance Issues (Enhanced)
A detailed audit of Exempt vs. Non-Exempt status.
- **Internal Checks**: Flags "Hourly" employees marked as "Exempt" in Uzio.
- **Cross-System Mismatches**: Flags when the FLSA status or Pay Type in Uzio does not match the source system (ADP/Paycom).
- **Context Fallback**: Includes the **Source Department Description** as a fallback reference because source "Job Titles" are frequently blank.

### 5. Data Quality Issues
Flags technically invalid data, such as `00/00/0000` placeholder dates or malformed SSNs.

---

## 4. Maintenance & Extension Guide

### Adding New Fields to Audit
1. Locate the `ADP_FIELD_MAP` or `PAYCOM_FIELD_MAP` in the respective `census_audit.py`.
2. Add your new field and its corresponding source system column name.
3. If the field needs specific normalization (like "Phone Number" or "Zip Code"), add a specialized comparison block in the `run_comparison` loop.

### Updating FLSA Logic
The FLSA audit is concentrated in the `flsa_rows` collection block. 
- **Variable Context**: You must ensure `adp_exists` or `p_i` is checked before pulling source values to avoid `KeyError`.
- **String Formatting**: Multiple detected issues should be combined using `; ` as a separator (e.g., *"Pay Type Mismatch; FLSA Mismatch"*).

### Adding New File Types
Modify `Selective Employee Extractor`. Add a new check that looks for a column name or sheet name unique to the new file type to trigger automatic detection.

---
*Created: April 2026*
