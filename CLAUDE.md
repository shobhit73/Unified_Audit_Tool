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

[apps/adp/](apps/adp/) and [apps/paycom/](apps/paycom/) mirror each other by design. Each has its own `census_audit`, `census_generator`, `deduction_audit`, `payment_audit`, `withholding_audit`, `emergency_audit`, `timeoff_audit`, `prior_payroll_generator`, and `total_comparison` module. When fixing a bug that applies to both vendors, check both trees — they diverge in field maps and vendor-specific quirks but share logic shape.

Vendor-agnostic tools live in [apps/common/](apps/common/) (`employee_extractor`, `paycom_combined_audit`).

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
