# Paycom Deduction Sanity Check

**Date:** 2026-10-08
**Status:** Implemented; `scratch/verify_paycom_deduction_sanity.py` passes on 25 real Paycom files
**Branch:** `rohit/paycom-deduction-sanity` (from `origin/main` @ `c8c283a`)
**Scope:** new `apps/paycom/deduction_sanity.py`, plus one sidebar entry and one route in `app.py`. It is the ADP Deduction Sanity Check copied and adapted; the ADP module is not touched.

## What the API does with the Paycom file (onboarding-service source)

`PaycomConfig` binds the CSV by header name. `PayComEmployeeDeductionValidator` runs the shared rules and adds Paycom-only ones:

- **Shared rules:**
  - EE Code, Deduction Code and Deduction Desc are mandatory.
  - **Exactly one** of Amount and Percent may be filled.
  - Amount must be ≥ 0, and Percent must be in 0–100.
  - The mapping is looked up by the **exact** Deduction Desc.
- **Paycom-only rules:**
  - **Tax Treatment** is mandatory and must start with `A -`, `B -` … `H -`.
  - **Start / Stop Date** must be `MM/dd/yyyy`, and `00/00/0000` means none. A blank Start Date counts as **today**, and the Stop Date must not be before it.
  - **Limit** must be `No` or `Yes (amount)`, and **Limit Accum** must be numeric.
- **The mapper passes Percent through as-is** (`Double.parseDouble(percent)`), so Paycom's `0.04` would be set up as 0.04%.

## Rules (Rohit)

| # | Rule |
|---|---|
| 1 | Remove a row whose **Stop Date is before the 1st of the current month** (on 08-Oct-2026 that is before 10/01/2026). A Stop Date inside the current month stays. |
| 2 | `00/00/0000` and blank Stop Dates stay. |
| 3 | **Percent × 100** (`0.04` → `4`); a blank stays blank. Applied only when the file writes fractions (see below). |
| 4 | Checkboxes per description, as in ADP. Garnishments, reimbursements, TapCheck, ZayZoon and Payactiv are pre-ticked. |
| 5 | Remove a row when **neither Amount nor Percent holds a non-zero value**. |
| 5a | Amount 0 with Percent 10 stays, and Amount 100 with Percent 0 stays (both are flagged, because the API takes only one). |
| 5b | Amount blank with Percent 0, Amount 0 with Percent blank, both 0, and both blank are all removed. |
| 6 | Terminated employees (`EE Status = T`) are left alone. |
| 7 | Everything else is as in ADP: flags only, the CSV keeps every column with no BOM, and an xlsx report is produced. |

### Percent format is detected per file
Chief Delivery and Spelman export **whole** percents (`5` = 5%, with not one fraction in the file). Multiplying them would turn 5% into 500%. So a file counts as fractional when **any non-zero Percent lies strictly between −1 and 1**, and only then is every Percent multiplied. The screen states what was detected and shows a **Multiply Percent by 100** checkbox that starts on the detected value and can be overridden.

The multiplication is exact decimal arithmetic, not float: `0.0745` → `7.45` and `1.72385` → `172.385`, which is then flagged as outside 0–100. Each changed cell gets a Change Log line with its old and new value.

### Pre-ticked descriptions (case and symbols ignored)
| Category | Rule | Seen in real files |
|---|---|---|
| Garnishment | word `SUPPORT`, `LEVY`, `LIEN` or `SPT`; a word starting `GARN` or `BANKRUPT`; `WAGE ASSIGN…` | Child Support (…$, %, - Fixed, $ 1–3), SUPPORT ORDER $ 1–3, ANNUAL SUPPORT FEE $, GARNISHMENT / GARN % 1, NEW YORK GARNISHMENT %, TAX LEVY % 1, BANKRUPTCY $, WAGE ASSIGNMENT % 1 (- MED), WAGE ASSIGN $/% 1, Lien |
| Reimbursement / earned-wage access | a word starting `REIM`; `PAYACTIV`, `ZAYZOON`, `TAPCHECK`, `EARNED WAGE` | Cell Phone, SH Cell Phone, Meal, Mileage, Expense, Tuition Reimburse, Employer Health Insurance Reim, Earned Wage Access |
| Not ticked | descriptions starting `LOA` | LOA Benefits / FSA / Medical Reimb: the employee paying benefits back during a leave, which is a real deduction |

### Flags (nothing changed)
These are checked on the rows that stay, after the Percent change:
- blank code or description; extra spaces around EE Code, Deduction Code, Deduction Desc, Tax Treatment or Company Match. Company Match `" []"` reads as a linked contribution to the API, because it compares against `"[]"`.
- Amount and Percent both filled; a value that is not a number; a negative Amount; a Percent outside 0–100.
- Tax Treatment blank or not starting with a code.
- Start or Stop Date not `MM/DD/YYYY`.
- Stop Date before the Start Date, where a blank Start Date counts as today. This catches a current-month Stop Date that has already passed.
- Limit not `No` / `Yes (amount)`; Limit Accum not a number.
- Duplicates: identical rows, or the same employee and description with a different code or amount.

### Hard stop
If `EE Code`, `Deduction Code`, `Deduction Desc`, `Amount`, `Percent`, `Tax Treatment` or `Stop Date` is missing, a red box names the column and no file is produced.

### Output
- `<Client>_Paycom_Deduction_Corrected.csv`: every original column, with only Percent changed. Plain UTF-8, no BOM.
- `<Client>_Paycom_Deduction_Sanity_<ts>.xlsx`, with these sheets:
  - **Corrected Data**
  - **Removed Rows**: each with every reason that applied
  - **Garnishments**
  - **Flagged Rows**
  - **Change Log**: removed rows and Percent changes

## Verification — `scratch/verify_paycom_deduction_sanity.py` (today fixed at 08-Oct-2026)

| Group | Must hold |
|---|---|
| rules | Rohit's zero table (9 cases); the Stop Date cutoff (9/30 removed; 10/1, 10/05, 00/00/0000 and blank kept); `scale_percent` (0.04→4, 0.00432→0.432, 1.72385→172.385, blank and text unchanged); 25 default ticks, including LOA Reimb, 401K and Health Savings left unticked |
| real (25 files) | kept + removed = source; no BOM, same headers, every non-Percent cell identical to the source; Percent exactly ×100 or untouched; no passed Stop Date and no all-zero row left; Change Log = removed rows + Percent changes |
| real | format detection: Banda and Stave are fractional, Chief and Spelman are whole; forcing ×100 on Chief flags its percents as outside 0–100 |
| manual | **Banda vs the file cleaned by hand on 05-Oct-2026: the same 405 rows kept, and the same Percent on all 162 rows with one** |
| synthetic | each Paycom flag on its own row; 0 + 10% kept and flagged; Stop 9/30 removed and 10/05 kept but flagged; Child Support on the Garnishments sheet; a missing Tax Treatment column refused |
| ui (AppTest) | the % box is ticked for Banda and unticked for Chief; unticking it changes no value; the default ticks; two downloads |

Hand-cleaned copies that disagree, and why:
- **Chief, 05-Jun:** 2 + 2 rows. By hand, two `VOL SP Life` rows with no Stop Date were removed, and two rows whose Stop Date had passed were kept. These are slips in the hand cleaning.
- **Stave "usable", 17-Aug:** cleaned under an older rule set that did not drop passed Stop Dates.
