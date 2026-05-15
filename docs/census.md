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

## 3. The Audit Report (Excel Schema)

The audit tool generates an Excel file with multiple tabs, each focusing on a specific audit dimension.

### Tab 1: Comparison Detail
The most granular report. Each row represents a single field audit for a single employee.
- **Columns**: `Employee ID`, `Employee Name`, `Field`, `Employment Status`, `Employment Status (Source)`, `UZIO_Value`, `SOURCE_Value`, `SOURCE_SourceOfTruth_Status`.

### Tab 2: ID Correlation (Identity Match)
Lists employees matched via SSN who have inconsistent IDs across platforms.
- **Usage**: Use this to identify where record IDs need to be synchronized in either system.

### Tab 3: Salaried Driver Exceptions
A safety check for logistics clients.
- **Trigger**: Job Title contains "Driver" AND Source Pay Type is "Salaried".

### Tab 4: FLSA Compliance Issues
Audits Exempt vs. Non-Exempt alignment.
- **Logic**: Checks for internal Uzio inconsistencies (Hourly/Exempt) and cross-system mismatches (Uzio Pay Type vs. Source Pay Type).

### Tab 5: Data Quality Issues
Identifies malformed data (e.g., `00/00/0000` dates) that requires manual cleanup in the source system.

---

## 4. Understanding Audit Statuses

The `SourceOfTruth_Status` column in the **Comparison Detail** tab uses specific categories to describe discrepancies:

| Status | Description |
| :--- | :--- |
| **Data Match** | Perfect match after normalization (e.g., identical names, formatted dates, or "Hourly" vs "hourly"). |
| **Data Mismatch** | Both systems have data, but the values are significantly different (e.g., different Birth Dates or Last Names). |
| **Value missing in Uzio** | A value exists in the Source system (ADP/Paycom) but is blank in Uzio. |
| **Value missing in Source** | A value exists in Uzio but is blank in the Source system. |
| **Active in Uzio** | Marked as "Active" in Uzio but either "Terminated/Inactive" in the source or missing entirely. Suggests a missing termination in Uzio. |
| **Terminated in Uzio** | Marked as "Terminated" in Uzio but "Active" in the source. Suggests a re-hire was processed in payroll but not updated in Uzio. |
| **Active in Source** | Marked as "Active" in ADP/Paycom but missing from Uzio entirely. Indicates employees that need to be onboarded. |
| **On Leave / Inactive** | Treated as **Active** if missing a termination date (with a prompt to exclude from payroll) or **Terminated** if a date is present. |
| **Terminated in Source** | Marked as "Terminated" in ADP/Paycom but still "Active" in Uzio. |
| **Employee ID Not Found in Uzio** | The Source ID (even after SSN correlation checks) does not exist in the Uzio export. |
| **Employee ID Not Found in Source** | The Uzio ID does not exist in the Source system export. |
| **Column Missing in Sheet** | The mapping refers to a column that was not found in the uploaded file (e.g., mapping expects "Personal Email" but the file lacks it). |

---

## 5. Maintenance & Extension Guide

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
