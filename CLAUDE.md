# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py        # opens http://localhost:8501
```

There is no test suite, linter config, or build step. The only runtime dependencies are `streamlit`, `pandas`, `openpyxl`, `xlsxwriter`, and `pyyaml`.

The Census Generator tools require [templates/Uzio_Census_Template.xlsm](templates/Uzio_Census_Template.xlsm) to exist on disk. It is a `.xlsm` with VBA that must be preserved through read/write; use `openpyxl` with `keep_vba=True` when opening it.

## Repository topology — THREE repos, mirror BEFORE you push

This working directory contains **three independent git repositories** as plain nested folders. There is **no `.gitmodules`** — they are NOT submodules, so a normal `git push` from the root reaches **only the root repo**.

| Path | Remote (SSH) | What it is |
|---|---|---|
| `.` (root) | `shobhit73/Unified_Audit_Tool` | Parent Streamlit app |
| `implementors_repo/` | `shobhitsharma-rgb/unified_audit_for_implementors` | Standalone "implementors" build of the **same** Streamlit app — its **own** Streamlit Cloud deployment |
| `audit_fast_api/` | `shobhit73/audit_fast_api_` | FastAPI + MCP server (no Streamlit UI) |

**`implementors_repo/` keeps byte-identical copies of `app.py`, `apps/`, and `utils/`.** It is a full mirror, not a slim fork. When you change any UI or app file in the root you MUST mirror it and push **both** repos to **their own remotes**:

1. Change the file(s) in the root → commit + push to `Unified_Audit_Tool`.
2. Copy the identical file(s) into `implementors_repo/<same path>` → commit + push to `unified_audit_for_implementors`.

**Pushing only the root is a silent production failure** — the implementors Streamlit Cloud app keeps serving stale code while the root repo looks correct. This already caused one missed deploy (the census-sanity plain-English UI redesign, May 2026: pushed to root only, the deployed implementors app still showed the old 3-column "Action Center").

Mirror matrix:
- Root **UI / app-logic** change (`apps/**`, `utils/ui_components.py`, `app.py`) → also mirror into `implementors_repo/`.
- Root **`utils/audit_utils.py`** change → also `implementors_repo/utils/audit_utils.py` **and** `audit_fast_api/` (the latter has its own slimmed `core/` port — apply the equivalent fix, don't blind-copy). See "MCP Sync" below.

All three remotes use **SSH**. Corporate TLS inspection kills HTTPS git operations on this machine — never re-point a remote to HTTPS.

## Architecture

### Single-router Streamlit app

[app.py](app.py) is a thin router. It renders a sidebar (Provider → Tool), then imports and calls a `render_ui()` / `render_census_sanity_check()` / `render_census_generator()` / `render_selective_census_generator()` function on the selected module.

Each router branch does `importlib.reload(module)` before calling the render function — this is intentional so edits to a tool module take effect on the next sidebar click without restarting Streamlit. Preserve this pattern when adding new tools.

### Parallel vendor tree

[apps/adp/](apps/adp/) and [apps/paycom/](apps/paycom/) mirror each other by design. Each has its own `census_audit`, `census_generator`, `deduction_audit`, `payment_audit`, `withholding_audit`, `emergency_audit`, `timeoff_audit`, `prior_payroll_generator`, `prior_payroll_setup_helper`, and `total_comparison` module. When fixing a bug that applies to both vendors, check both trees — they diverge in field maps and vendor-specific quirks but share logic shape.

The Paycom side has its own [apps/paycom/prior_payroll_setup_helper.py](apps/paycom/prior_payroll_setup_helper.py) (replaces the deleted `deduction_analyzer.py`). It mirrors the ADP setup helper but takes both a Paycom Prior Payroll Register AND a Paycom Scheduled Deductions Report. Pre-tax vs post-tax classification is read straight from the Scheduled Deductions `Tax Treatment` column (`B` = Section 125 pre-tax, `H` = 401k traditional pre-tax, `A` = post-tax) — no empirical algorithm needed since Paycom labels each deduction directly. Bonus FLSA test uses Strategy A+C: when both `OT` (plain) and `WOT` (Paycom's Weighted Overtime) lines exist for the same employee+period, compare them; WOT > OT means the bonus was rolled in => non-discretionary. Otherwise indeterminate.

**Asymmetric modules (ADP-only, no Paycom equivalent):**
- [apps/adp/prior_payroll_sanity.py](apps/adp/prior_payroll_sanity.py) — cleans an ADP Prior Payroll export (drops `Totals For Associate ID` summary rows, removes the bottom-of-file grand-total row, aggregates per-pay-period exports back to one row per associate, optional NET PAY ⇄ TAKE HOME value swap). ADP money cells store `=ROUND(x, 2.0)` Excel formulas — pandas reads those as null, so this module reads via openpyxl + a small formula evaluator. **The UI now runs `detect_file_shape()` on upload before asking the user anything**: it shows the facts (associates, total rows, max rows/associate, date span, distinct pay dates, period range) plus a recommendation (`full_quarter` for ≥80-day per-pay-period exports, `preserve_pay_periods` for ≤40-day partials, no recommendation when already 1 row/associate or when ambiguous). The Aggregation Strategy radio is pre-selected to the recommendation but always editable — the user must explicitly confirm before the Run button takes effect.
- [apps/adp/prior_payroll_setup_helper.py](apps/adp/prior_payroll_setup_helper.py) — discovers what to configure in Uzio for a fresh ADP prior payroll migration. Given a sanitized prior payroll file plus the State Tax Code master CSV, emits an Excel workbook + standalone Tax_Mapping CSV with: every distinct earnings code (with $/hours/avg rate), contributions vs deductions (split by name pattern), **pre-tax vs post-tax verdict per deduction** (subset-sum on `TOTAL EARNINGS − FIT_TAXABLE`; one positive proof = pre-tax for everyone), tax mapping in the `Payroll_Mappings_Tax_Mapping_CORRECTED` format (1 row per fed tax, 1 row per state for SIT/SDI/SUTA/FLI), and an FLSA bonus discretionary/non-discretionary verdict. Reuses the `=ROUND()` formula evaluator from `prior_payroll_sanity.py`.

Vendor-agnostic tools live in [apps/common/](apps/common/) (`employee_extractor`, `paycom_combined_audit`).

### Prior Payroll Audit Tool routing gotcha

The sidebar entry `"ADP - Prior Payroll Audit Tool"` in [app.py](app.py) routes to [apps/adp/total_comparison.py](apps/adp/total_comparison.py) — **not** to a `prior_payroll_audit.py` file. There used to be a stale parallel fork (`apps/adp/prior_payroll_audit.py`) that was unreachable from the sidebar; it was deleted in commit `301cddf`. The same convention is on the Paycom side: `"Paycom - Prior Payroll Audit Tool"` → [apps/paycom/total_comparison.py](apps/paycom/total_comparison.py). When asked to add features to the prior-payroll audit, edit `total_comparison.py`, not anything else.

The `total_comparison.py` audit reports for both vendors now include three additional sheets beyond the original Full Comparison / Mismatches Only / Employee Mismatches: **Duplicate Pay Periods** (UZIO-side skeleton-vs-detail row pairs), **Pay Stub Counts** (per-employee distinct Pay Date count, ADP combined vs UZIO), and **Tax Rate Verification** (SS / Medicare / FUTA + per-state SUTA, effective rate vs standard at 0.05% tolerance). Paycom's tax rate sheet uses long-format Description-row matching for the Paycom side; ADP's uses tax-mapping plus sibling-column heuristics for wages. UZIO-side wages always come from the section-header structure.

### Census generator is three tools in one module

`apps/{adp,paycom}/census_generator.py` exposes three render entry points that the router dispatches to separately:

- `render_census_sanity_check()` — validates the source, shows findings on screen, and produces a downloadable **Corrected Source** (.xlsx with a `Change Log` sheet)
- `render_census_generator()` — full ADP/Paycom → Uzio template conversion
- `render_selective_census_generator()` — update specific columns in an existing Uzio template

They share the same field-map dictionary at the top of the file and the same `utils.audit_utils.generate_uzio_template()` backend.

### Census Sanity Check — backend / UI / Change Log (keep all three in sync)

The Census Sanity Check has three layers. **Never apply a transformation in one layer without reflecting it in the other two** — every change to the user's data must be both shown on screen and recorded in the Change Log. There are no silent transformations.

**Layer 1 — Backend** (applied to the downloaded Corrected Source, inside `render_census_sanity_check`'s download block):

*Per-employee fixes* — each writes one Change Log row via the local `log_change()`:
- FLSA: Driver/Walker/Helper job titles forced to Non-Exempt + Hourly; blank FLSA filled from Pay Type; unresolvable FLSA left blank and flagged.
- Smart Driver: blank Job Title / FLSA / Pay Type filled for Driver-like roles from Department.
- Blank Job Title → "Driver" for Non-Exempt Hourly employees.
- Blank Work Email → filled from Personal Email.
- Status: On Leave / Inactive → Active (no term date) or Terminated (has term date); Intern → Part-Time; blank Employment Type → Full Time.
- Zip codes padded / trimmed / cleaned to 5 digits.
- Emergency-contact relationship starting "Fian" → "Fiancee".
- Working Hours → 0 for **every** employee (hourly and salaried, blank or filled).

*File-wide standardizations* — each writes ONE summary Change Log row via the local `log_summary()` (Employee ID = `(All employees)`):
- All date columns → MM/DD/YYYY.
- Columns reordered (key fields first).
- Rows reordered to cluster each manager with their reportees (only when a reporting hierarchy exists).
- ADP only: home-zip column header → "Primary Address: Zip Code"; Gender column populated from the Sex column.

**Layer 2 — UI** (on screen, before download):
- `render_validation_results()` — three sections: red "Needs your attention" (hard errors), green "Fixed automatically", amber "Please review". Issue text is GENERIC (no per-employee values such as a job title or state name) so each issue type collapses to one consolidated line; per-employee detail stays in the "View the full list" table.
- `render_standardization_notice()` — one info box listing the file-wide standardizations.
- `render_duplicate_column_error()` / `render_missing_column_error()` — hard-stop screens: if a column is duplicated, or a `REQUIRED_CENSUS_FIELDS` column is missing, `preprocess_*_file()` returns `None` and **no census file is produced**.

**Layer 3 — Change Log** (a `Change Log` sheet inside the downloaded .xlsx):
- One row per per-employee fix (`log_change`): Employee ID, Name, Field Changed, Old Value, Assumed Value, Comments.
- One summary row per file-wide standardization (`log_summary`): Employee ID = `(All employees)`.

When adding a new auto-fix: decide whether it is per-employee (`log_change`) or file-wide (`log_summary`), and add it to `render_standardization_notice` or the relevant validation list so the user is told on screen. The census-sanity logic is mirrored in the API at `audit_fast_api/core/census/sanity_check.py` (`generate_corrected_census_xlsx`).

### Shared engine: utils/

- [utils/audit_utils.py](utils/audit_utils.py) — the core engine: `generate_uzio_template()`, `validate_source_data()`, `inject_into_uzio_template()`, `selective_update_uzio()`, plus shared helpers (`check_duplicate_columns`, `format_datetime_strings`, `US_STATE_TO_ABBR`). All auto-fix logic (Driver rule, FLSA alignment, DOL default, email fallback, zip normalization) lives here.
- [utils/preprocess_source_data.py](utils/preprocess_source_data.py) — opt-in auto-fix scanning applied *after* sanity checks are shown. Do not fold this back into `validate_source_data` — sanity reporting must stay read-only.
- [utils/withholding_core.py](utils/withholding_core.py) — shared withholding comparison logic; used by both ADP and Paycom withholding audits.
- [utils/ui_components.py](utils/ui_components.py) — UI primitives: `inject_premium_styles`, `render_premium_header`, plus the census-sanity components `render_validation_results`, `render_standardization_notice`, `render_duplicate_column_error`, `render_missing_column_error`, the `REQUIRED_CENSUS_FIELDS` list and the `_plain_english_issue` translator. (`render_finding_card` still exists but is no longer used.)

### Withholding config lives in key_mapping.yml

[key_mapping.yml](key_mapping.yml) (~86KB) is the single source of truth for federal and per-state withholding field labels, sections, and payslip inclusion flags. Withholding audit modules read this file — don't hardcode labels in Python.

### File I/O conventions

- Source data is always loaded with `dtype=str` to preserve leading zeros (SSN, zip, employee IDs). Don't let pandas auto-coerce.
- Uploaded files are `BytesIO` streams — always `file_obj.seek(0)` after a peek-read (headers, duplicate check) before the real parse.
- Inputs accept both `.xlsx` and `.csv`; the sniffing happens in `check_duplicate_columns` and the per-tool loaders.

### CSV output rule — NEVER WRITE A UTF-8 BOM. **NON-NEGOTIABLE.**

**Every CSV this codebase produces MUST be plain UTF-8 with NO byte-order mark.** This is a product requirement set by the downstream API team — our APIs match the first column header *literally* (e.g. `Associate ID`, `Employee_Code`), so a BOM smuggles `U+FEFF` in front of the first header and the column lookup silently misses. We have already shipped at least one customer-impacting incident from this (Skyland, May 2026).

**Forbidden — never do this:**

```python
# ❌ utf-8-sig writes EF BB BF before the first byte
df.to_csv(path).encode("utf-8-sig")
df.to_csv(path, encoding="utf-8-sig")
io.open(path, "w", encoding="utf-8-sig")
```

**Required:**

```python
# ✅ plain UTF-8, no BOM
df.to_csv(path).encode("utf-8")
df.to_csv(path, encoding="utf-8")
df.to_csv(path)  # pandas default is also bare utf-8 — fine
```

The "but Excel needs the BOM to render UTF-8 correctly" rationale that historically justified `utf-8-sig` is **not a valid reason** here. Every sanity / generator tool that produces a CSV also produces an XLSX from the same DataFrame; route Excel users to the XLSX download. The CSV is for API ingestion only.

**Mirror enforcement:** this rule applies to root, `implementors_repo/`, and `audit_fast_api/`. Before merging any change that calls `to_csv` or writes a `.csv` file, grep the diff for `utf-8-sig` / `utf_8_sig` — they must not appear in encoding arguments. (They MAY appear in comments explaining this rule; that's fine.)

## UI rules (non-obvious)

[frontend.md](frontend.md) is load-bearing — **read it before any CSS change**. Key constraints that break the app if violated:

- Never apply `* { font-family: ... }` or `html, body { ... }` globally. It strips Streamlit's SVG icons (expander arrows, etc.). Scope to `.stMarkdown p, .stMarkdown span, ...` or use `:not(svg):not(i)`.
- Wrap long result lists in `st.container(height=400, border=True)` to prevent infinite scroll.
- Consolidate duplicate findings by regex-stripping parenthesized details before grouping: `re.sub(r'\(.*?\)', '', issue)`.
- Every error row must carry the affected Employee IDs — no orphan findings.

## Gitignore gotchas

[.gitignore](.gitignore) excludes all `*.xlsx`, `*.xls`, `*.csv` — so test data and input files won't be committed. Two explicit exceptions:

- `Deduction Analyzer/Deduction Setup Config.xlsx` is force-included (it's config, not data).
- `templates/Uzio_Census_Template.xlsm` is `.xlsm` so it's not caught by the filter — it's tracked.

`Sample Data/` is excluded entirely (contains real employee data).

## Standard Uzio Job Titles (Company Master reference)

The canonical Uzio **Company Master → Job Titles** list for a DSP company. Uzio groups every job title under a **Job Category** (`Owner`, `Overhead Staff`, `Delivery Associates`, `Non-DSP`). This is the source of truth the census tools' `ALLOWED_JOB_TITLES` (in `apps/{adp,paycom}/census_generator.py`) and `HOURLY_ONLY_JOB_TITLES` (in `utils/audit_utils.py`) should align with. **30 titles** total:

| Code | Job Category | Job Title |
|---|---|---|
| 001 | Owner | DSP Owner |
| 002 | Overhead Staff | Operations Manager |
| 003 | Overhead Staff | Operations Lead |
| 004 | Overhead Staff | Fleet Manager |
| 005 | Overhead Staff | Safety Manager |
| 006 | Overhead Staff | Performance Manager |
| 007 | Overhead Staff | Trainer |
| 008 | Overhead Staff | Human Resources |
| 009 | Overhead Staff | Recruiter |
| 010 | Overhead Staff | Office Personnel |
| 011 | Overhead Staff | Payroll Assistant |
| 012 | Overhead Staff | Finance |
| 013 | Overhead Staff | Dispatch |
| 014 | Overhead Staff | Management |
| 015 | Overhead Staff | Admin |
| 016 | Overhead Staff | Survey |
| 017 | Overhead Staff | Warehouse |
| 018 | Delivery Associates | Walker |
| 019 | Delivery Associates | Driver |
| 020 | Delivery Associates | Helper |
| 021 | Delivery Associates | Driver-Lite |
| 022 | Delivery Associates | Driver-Step Van |
| 023 | Delivery Associates | Driver-Unscheduled |
| 024 | Delivery Associates | Lead Driver |
| 025 | Delivery Associates | DDU Dedicated |
| 026 | Delivery Associates | DDU Shared |
| 027 | Non-DSP | Non-DSP Related |
| 028 | Delivery Associates | Driver -Major Appliance |
| 029 | Delivery Associates | E-Biker |
| 030 | Delivery Associates | TSO-PV Driver |

**`Delivery Associates` is a Job *Category*, not a job title** — the 12 titles under it (Walker, Driver, Helper, Driver-Lite, Driver-Step Van, Driver-Unscheduled, Lead Driver, DDU Dedicated, DDU Shared, Driver -Major Appliance, E-Biker, TSO-PV Driver) are the ones Uzio treats as Hourly / Non-Exempt. The `HOURLY_ONLY_JOB_TITLES` roster in code is the force-Hourly/Non-Exempt set and matches this category. `E-Biker` and `TSO-PV Driver` were added to the roster. `delivery associate` / `delivery associates` are intentionally **kept** in the roster (even though Uzio uses it only as a category name) because the literal string arrives as an actual Job Title in ADP/Paycom source exports.

**Two opposite job-title rules (don't confuse them):**
- **Driver rule (auto-fix):** a hourly-only title (Driver/Walker/E-Biker/…) marked Salaried or with blank FLSA is *force-set* to Hourly + Non-Exempt on download.
- **Manager rule (flag-only):** a non-delivery title (DSP Owner, any Overhead Staff role, Non-DSP Related, or any unrecognized title) marked **Hourly** and/or **Non-Exempt** is **flagged for review and left UNCHANGED** — surfaced in the amber "Please review" UI box (`manager_hourly_flags`) and recorded in the Change Log as "(No change — please review)". Blank job titles are excluded (handled by the Driver-default logic).

## External reference — Uzio onboarding API source

The backend onboarding / census-ingestion logic lives **outside this repo**, on local
disk. When you need the EXACT rules the onboarding API enforces during an ADP/Paycom
migration (how gender, payment methods, deductions, taxes etc. are validated and
mapped), **Read/Grep the local path instead of guessing** — do NOT reverse-engineer it
from the sanity tools alone.

- Local path (actionable — Claude can Read/Grep this directly):
  `C:\Users\shobhit.sharma\Downloads\Uzio Code\onboarding\onboarding-service\`
- Git remote (human reference only — internal server, NOT cloneable from a fresh session):
  `https://git.internal.uzio.com/git/onboarding`

Useful entry points under that path:
- `src/main/java/com/uzio/onboarding/enums/Gender.java` — accepted gender values (Male/Female/M/F/Intersex; everything else → null).
- `src/main/java/com/uzio/onboarding/validator/EmployeeCensusValidator.java` — per-field census validation (gender, race, pronouns, disability, …).
- `src/main/java/com/uzio/onboarding/mapper/EmployeeCensusMapper.java` — source columns → Uzio person/employee model.
- `src/main/java/com/uzio/onboarding/model/EmployeeMasterPaycom.java` / `EmployeeMasterADP.java` — CSV column bindings per vendor.
- `src/main/java/com/uzio/onboarding/validator/impl/adp/ADPPaymentMethodValidator.java` — the 5 payment-method group rules.

(The wider `Uzio Code` folder holds other Uzio repos too; it is not itself a single git repo.)

## Docs to consult

- [README.md](README.md) — full architecture diagrams, module reference, field mappings (ADP→Uzio, Paycom→Uzio), and the auto-fix rule catalog with code snippets.
- [docs/SOP.md](docs/SOP.md) — end-user operating procedure; useful when a bug report describes the workflow in user terms.
- [frontend.md](frontend.md) — mandatory before UI work (see above).
- [CHANGELOG.md](CHANGELOG.md) — record of all functional changes and standardizations.

## Recent Platform Evolution (May 2026)

The platform recently underwent a "Census Hardening" phase. Key logic changes to preserve:

1.  **Leave/Inactive Management**: Employees marked "On Leave" or "Inactive" in source systems are automatically converted to **Active** if their termination date is blank (with a "Excluded from payroll" comment). If a termination date is present, they are marked **Terminated**.
2.  **Forced Driver FLSA**: Any Job Title containing "Driver" or "Helper" is now strictly **Non-Exempt** and **Hourly**, overriding both source values and user defaults.
3.  **Emergency Contact Fix**: Any relationship string starting with "Fian" is auto-corrected to **"Fiancee"** to satisfy Uzio validation.
4.  **Full-Time Standard**: Always use **"Full Time"** (no hyphen) for employment types.
5.  **MCP Sync**: The `audit_fast_api/` server logic is now synchronized with the Streamlit app's census generator. Any change to `utils/audit_utils.py` in the root should be mirrored to `audit_fast_api/utils/audit_utils.py`.
