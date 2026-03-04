# Standard Operating Procedure (SOP) - Unified Audit Tool

## 1. Introduction
This Unified Audit Platform allows you to audit and reconcile data between **Uzio** and external payroll providers like **ADP** and **Paycom**. The tool automates the comparison process, identifying discrepancies, missing values, and data gaps.

**Target Audience:** Implementation Teams and Data Auditors.

---

## 2. General Instructions

### How to Access the Tool
1.  Open the application URL (or run `streamlit run app.py` if running locally).
2.  You will see a sidebar on the left with the title **"Audit Hub"**.
3.  First, select the **Provider** (ADP or Paycom).
4.  Then, use the specific **"Select Tool"** menu to choose the audit module you need.

### File Requirements (Universal)
*   **Format:** All input files must be in **Excel (.xlsx)** format.
*   **Protection:** Files must not be password protected.
*   **Headers:** Ensure column headers are in the first row of each sheet.

### 💡 General Reporting & Filtering Strategy
For all tools, the general workflow to find errors is:
1.  Open the **Excel Output Report**.
2.  Go to the **Comparison Details** (or *Audit Details*) tab.
3.  **Enable Filters** in Excel (`Data` -> `Filter`).
4.  Go to the **Status** column (e.g., `Status` or `ADP_SourceOfTruth_Status`).
5.  **UNCHECK** the box for `"Data Match"`.
6.  **CHECK** all other boxes (Mismatch, Missing Value, etc.).
7.  **Result:** You will now see *only* the records that need attention.

---

## 3. Tool-Specific Instructions

### A. Deduction Audit
**Purpose:** Compares deduction amounts between ADP and Uzio to ensure payroll accuracy.

**Input File Preparation:**
Prepare a single Excel file with **3 Sheets**:
1.  **`Uzio Data`**: Must contain *Employee ID*, *Deduction Name*, and *Amount* (or *Percentage*).
2.  **`ADP Data`**: Must contain *Associate ID*, *Deduction Code*, and *Deduction Amount*.
3.  **`Mapping Sheet`**: Maps ADP Codes to Uzio Deduction Names.
    *   **Column A:** ADP Deduction Code/Description
    *   **Column B:** Uzio Deduction Name

**Understanding the Report:**
The report contains three main sheets:
*   **`Summary`**: High-level metrics.
*   **`Field_Summary_By_Status`**: Counts of matches/mismatches per field.
*   **`Comparison_Detail_AllFields`** (or *Audit Details*): The core row-by-row comparison.
    *   **Key Column:** `Status`
    *   **Values:**
        *   `Data Match`: Difference is less than $0.01. (Ignore)
        *   `Data Mismatch`: Amounts differ. **Action:** Check calculating logic or update Uzio/ADP.
        *   `Value Missing in Uzio (ADP has Value)`: Employee has a deduction in ADP but nothing in Uzio. **Action:** Add deduction to Uzio.
        *   `Value Missing in ADP (Uzio has Value)`: Employee has a deduction in Uzio but nothing in ADP. **Action:** Verify if deduction should allow skipping.
        *   `Employee Missing...`: The ID exists in one file but not the other.

---

### B. Prior Payroll Audit
**Purpose:** Transforms "Prior Payroll" input files (often wide format with multiple pay dates) into a consolidated report compared against Uzio.

**Input File Preparation:**
Single Excel file with **3 Sheets**:
1.  **`Uzio Data`**: Standard census/deduction data.
2.  **`ADP Data`** (or "Prior Payroll"): Contains *Associate ID* and *Pay Date* columns.
3.  **`Mapping Sheet`**: Maps ADP header names to standardized Output names.

**Understanding the Report:**
The report helps reconcile historical payroll data.
*   **Sheet:** `Audit Details` output with columns like `Pay_Date`, `Deduction_Name`.
*   **Status Logic:** Same as *Deduction Audit*.
*   **Filtering:** Filter by `Pay_Date` to audit specific payroll periods.

---

### C. Census Audit (ADP vs Uzio)
**Purpose:** Compares demographic data (Name, Address, SSN, Dates) between ADP and Uzio.

**Input File Preparation:**
Single Excel file with **3 Sheets**:
1.  **`Uzio Data`**: Must contain *Employee ID*.
2.  **`ADP Data`**: Must contain *Associate ID*.
3.  **`Mapping Sheet`**:
    *   **Column "Uzio Coloumn"**: Header name in Uzio sheet.
    *   **Column "ADP Coloumn"**: Header name in ADP sheet.

**Understanding the Report:**
*   **Sheet:** `Comparison_Detail_AllFields`
*   **Sheet:** `FLSA_Compliance_Issues` (*New*)
    *   Identifies invalid combinations like **Hourly** Pay Type with **Exempt** FLSA Classification.
*   **Sheet:** `Active_Missing_In_Uzio` (*New*)
    *   Lists employees active in ADP but typically missing from Uzio (useful for catching new hires not yet entered).
*   **Status Column:** `ADP_SourceOfTruth_Status`
*   **Status Code Meanings:**
    *   `Data Match`: Values match (handling case, spacing, and date formats automatically).
    *   `Data Mismatch`: Real difference found. (e.g. "Smith" vs "Smyth").
    *   `Active in Uzio`: (Field: *Employment Status*) Employee is Active in Uzio but Terminated/Retired in ADP. **Action:** Terminate in Uzio?
    *   `Terminated in Uzio`: (Field: *Employment Status*) Employee is Terminated in Uzio but Active in ADP.
    *   `Value missing in...`: Field is blank in one system but populated in the other.

---

### D. Payment & Emergency Audit
**Purpose:** Audits Bank Account details and Emergency Contacts.

**Input File Preparation:**
Single Excel file with **5 Sheets**:
1.  **`Uzio Data`**
2.  **`ADP Payment Data`**
3.  **`ADP Emergency Contact Data`**
4.  **`Payment_Mapping`**: Maps Uzio Payment fields to ADP Payment fields.
5.  **`Emergency_Mapping`**: Maps Uzio Emergency fields to ADP Emergency fields.

**Understanding the Report:**
This tool generates **two independent reports**:
1.  **Payment Report**: Variances in Net/Gross Pay.
2.  **Emergency Contact Report**: Mismatches in emergency contact details.
*   **Logic:** It intelligently compares "Flat Dollar Amount" vs "Percentage" distributions.
*   **Status:** `Data Mismatch` here often means a bank account number typo or a distribution priority mismatch.

---

### E. Paycom Census Audit
**Purpose:** Audits Paycom census data against Uzio (Alternative to ADP Census).

**Input File Preparation:**
Single Excel file with **3 Sheets**:
1.  **`Uzio Data`**: Must contain *Employee ID*.
2.  **`Paycom Data`**: Must contain *Employee Code*.
3.  **`Mapping Sheet`**:
    *   **Column "Uzio Column"**: Header in Uzio sheet.
    *   **Column "Paycom Column"**: Header in Paycom sheet.

**Understanding the Report:**
*   **Sheet:** `Comparison_Detail_AllFields`
*   **Sheet:** `FLSA_Compliance_Issues`: Checks generally for Pay Type vs FLSA mismatches.
*   **Sheet:** `Active_Missing_In_Uzio`: Lists active Paycom employees not found in Uzio.
*   **Key Logic:**
    *   Paycom "On Leave" is treated as "Active".
    *   "Salaried" (Uzio) matches "Salary" (Paycom).
*   **Status:** Similar to standard Census Audit. Use filters to identify specific field discrepancies like DOB or Salary mismatches.

---

### F. Paycom Withholding Audit (FIT/SIT)
**Purpose:** Audits Federal and State Income Tax withholding setups between Paycom and Uzio.

**Input File Preparation:**
You need **3 files** (CSV and Excel):
1.  **`Paycom Data` (CSV)**: Wide format export from Paycom. Must contain Employee ID and Tax/Status columns.
2.  **`Uzio Data` (CSV)**: Long format export. Columns: `employee_id`, `withholding_field_key`, `withholding_field_value`.
3.  **`Mapping Sheet` (Excel)**:
    *   **Column "Uzio Field Key"**: The key from the Uzio CSV (e.g., `FIT_FILING_STATUS`).
    *   **Column "PayCom Column"**: The header name in the Paycom CSV.

**Optional Files:**
*   `key_mapping.yml`: For pretty labels in the UI.
*   `filing status_code.txt`: For mapping numeric status codes to text labels.

**Understanding the Report:**
*   **Unique Logic:**
    *   **Amounts:** Uzio amounts (often cents) are converted to dollars (/100) to match Paycom.
    *   **Booleans:** Maps "Yes/Y/1" to "True" automatically.
    *   **Filing Status:** Uses "substring matching" to handle minor differences (e.g., "Single" vs "Single/Married at Single Rate").
*   **Status Codes:**
    *   `Data Match`: Logic confirmed match.
    *   `Data Mismatch`: Real difference.
    *   `Value missing in...`: One side has data, the other is blank.

---

### G. ADP Withholding Audit
**Purpose:** Audits Federal and State Income Tax withholding setups between ADP and Uzio.

**Input File Preparation:**
You need **3 files** (CSV or Excel):
1.  **`ADP Export`**: Wide format export from ADP (one row per employee). Must contain Associate ID and relevant Tax/Status columns.
2.  **`UZIO Withholding Export`**: Long format export. Columns: `employee_id`, `withholding_field_key`, `withholding_field_value`.
3.  **`Mapping Sheet`**: Excel file mapping keys.
    *   **Column "Uzio Columns"**: Key from Uzio file (e.g., `FIT_FILING_STATUS`).
    *   **Column "ADP Columns"**: Header name in ADP file.

**Understanding the Report:**
*   **Logic:** Uses the same core logic as the Paycom Withholding tool (cents to dollars, boolean normalization, etc.).
*   **Unique Feature:** Allows filtering by "Active Status" to exclude terminated employees from the audit.

---
### H. Paycom Payment Audit
**Purpose:** Audits Paycom payment (bank) data against Uzio to ensure direct deposit accuracy.

**Input File Preparation:**
You need a single Excel file with **2 Sheets**:
1.  **`Uzio Data`**: Standard Uzio export containing Employee ID, Routing Number, Account Number, Amount/Percent.
2.  **`Paycom Data`**: Wide format export from Paycom (Net Pay + Distributions 1-8).
*   **No Mapping Sheet Needed:** The tool automatically detects relevant columns.

**Understanding the Report:**
*   **Logic:**
    *   **Auto-Unpivot:** The tool converts Paycom's wide format (Net + Dist_1...Dist_8) into a list of accounts per employee.
    *   **Matching:** Accounts are matched based on **Routing Number + Account Number**.
*   **Status Messages:**
    *   `Data Match`: Account details (Type, Amount, Percent) match.
    *   `Data Mismatch`: Account found but details differ (e.g., Checking vs Savings, or 100% vs Flat Amount).
    *   `Employee ID not found...`: Employee exists in one file but not the other.
    *   `Account in [System] not found in [Other]`: An account exists in one system (e.g., Paycom) but has no matching Routing/Account pair in the other (e.g., Uzio).

---

### I. ADP Census Generator
**Purpose:** Transforms an unstructured ADP census export into the standard Uzio template format to prepare for system import.

**Input File Preparation:**
A single Excel or CSV file direct from ADP containing employee demographics.

**Understanding the Process:**
1. Upload the source file. The system will automatically run **Sanity Checks**.
2. **Critical Errors:** If columns are missing or values are fundamentally invalid, the tool displays a summary report of errors. You can download these or ignore them (non-blocking).
3. **Auto-Fix Options:** Uses checkboxes to automatically:
   * **Fix Zip Codes:** Truncates zip codes after a dash (e.g., `12345-6789` -> `12345`) and zero-pads leading digits (e.g., `123` -> `00123`).
   * **Missing Work Email Fallback:** Swaps in Personal Email if Work Email is blank.
   * **Blank Working Hours:** Can automatically set blank schedules to 0.
4. **Mapping:** Manually map your source Job Titles and Work Locations to the system-allowed list.
5. Click Generate. The tool outputs a standardized Uzio`.xlsm` file.

---

### J. Paycom Census Generator
**Purpose:** Transforms a Paycom census export into the standard Uzio template.

**Input File Preparation:**
A single Excel or CSV file from Paycom.

**Understanding the Process:**
1. Upload the Paycom source file.
2. **DSP Owner Detection:** The tool will automatically scan for the most frequent `Supervisor_Primary_Code`. It will display a blue banner identifying the DSP Owner. Leave the checkbox checked to automatically set their Position to `"DSP Owner"` and sort them to the **very top** of both the corrected source file and the final Uzio output template.
3. **Paycom Specific Validations:**
   * Enforces hard stops if `DOL_Status` or `Employee Status` are blank.
   * If `Position` is blank, it automatically checks variations of `Department Description` to use as a fallback. A blue banner will show if this fallback was used.
4. **Auto-Fix Options:** Similar to ADP, select checkboxes to fix FLSA Statuses, working hours, and zip codes.
5. Provide mapping for Titles/Locations and Generate.

---

### K. Paycom Prior Payroll Generator
**Purpose:** Converts a generic Paycom prior payroll CSV/XLSX into the Uzio template format, handling summation and column alignment.

**Input File Preparation:**
You need **2 files**:
1. **`Paycom Prior Payroll File`**: The raw export from Paycom.
2. **`Blank Uzio Template`**: A blank template containing the specific dynamic headers expected for this client.

**Understanding the Process:**
1. Upload the Paycom file and the blank Uzio Template.
2. The tool uses intelligent **Auto-Mapping** (`difflib`) to pre-select dropdowns based on string similarity (e.g., it will guess that "401k" maps to "401(k) ER").
3. Review the dropdowns. You can assign columns to be mapping, auto-summed (for net pay distributions), or "Skipped".
4. Review the **Final Mapping Review** table.
5. Click Generate to download the consolidated template. The tool includes built-in logic to ensure `Gross - Taxes - Deductions = Net`.

---

## 4. Troubleshooting common issues
*   **"Missing Tabs" Error:** Check that your Excel sheet names match the requirements exactly.
*   **"Column Missing" Error:** Ensure the Mapping Sheet refers to exact column headers found in the Data sheets.
*   **Empty Report:** Check if the *Employee IDs* match between the two systems (e.g., one has leading zeros, one doesn't).
