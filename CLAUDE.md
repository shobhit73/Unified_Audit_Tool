# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py        # opens http://localhost:8501
```

There is no test suite, linter config, or build step. The only runtime dependencies are `streamlit`, `pandas`, `openpyxl`, `xlsxwriter`, and `pyyaml`.

The Census Generator tools require [templates/Uzio_Census_Template.xlsm](templates/Uzio_Census_Template.xlsm) to exist on disk. It is a `.xlsm` with VBA that must be preserved through read/write; use `openpyxl` with `keep_vba=True` when opening it.

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

- `render_census_sanity_check()` — validation-only, no output file
- `render_census_generator()` — full ADP/Paycom → Uzio template conversion
- `render_selective_census_generator()` — update specific columns in an existing Uzio template

They share the same field-map dictionary at the top of the file and the same `utils.audit_utils.generate_uzio_template()` backend.

### Shared engine: utils/

- [utils/audit_utils.py](utils/audit_utils.py) — the core engine: `generate_uzio_template()`, `validate_source_data()`, `inject_into_uzio_template()`, `selective_update_uzio()`, plus shared helpers (`check_duplicate_columns`, `format_datetime_strings`, `US_STATE_TO_ABBR`). All auto-fix logic (Driver rule, FLSA alignment, DOL default, email fallback, zip normalization) lives here.
- [utils/preprocess_source_data.py](utils/preprocess_source_data.py) — opt-in auto-fix scanning applied *after* sanity checks are shown. Do not fold this back into `validate_source_data` — sanity reporting must stay read-only.
- [utils/withholding_core.py](utils/withholding_core.py) — shared withholding comparison logic; used by both ADP and Paycom withholding audits.
- [utils/ui_components.py](utils/ui_components.py) — `inject_premium_styles`, `render_premium_header`, `render_finding_card` (the "Editorial Ledger" UI primitives).

### Withholding config lives in key_mapping.yml

[key_mapping.yml](key_mapping.yml) (~86KB) is the single source of truth for federal and per-state withholding field labels, sections, and payslip inclusion flags. Withholding audit modules read this file — don't hardcode labels in Python.

### File I/O conventions

- Source data is always loaded with `dtype=str` to preserve leading zeros (SSN, zip, employee IDs). Don't let pandas auto-coerce.
- Uploaded files are `BytesIO` streams — always `file_obj.seek(0)` after a peek-read (headers, duplicate check) before the real parse.
- Inputs accept both `.xlsx` and `.csv`; the sniffing happens in `check_duplicate_columns` and the per-tool loaders.

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
