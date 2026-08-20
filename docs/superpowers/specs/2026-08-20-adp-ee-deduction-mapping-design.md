# ADP Prior Payroll Setup Helper — Employee Deduction Mapping file

**Date:** 2026-08-20
**Status:** Approved for implementation
**Scope:** `apps/adp/prior_payroll_setup_helper.py` (ADP only — no Paycom change)

## Problem

The ADP setup helper emits four Source → UZIO mapping CSVs that the onboarding API
consumes alongside the prior payroll upload. Assigning those deductions to
individual employees is a **separate** API call that takes a **different** source
file — ADP's *Voluntary Deduction* export — and its own mapping CSV. Today that
fifth mapping file is built by hand.

It cannot be built from the existing `_Deductions_mapping.csv`, because that file's
`Source Deduction Code Name` is the prior payroll **column header**
(`VOLUNTARY DEDUCTION : LTD-LTD POST TAX`), while the employee-deduction API matches
on the Voluntary Deduction file's `DEDUCTION DESCRIPTION` (`LTD Post Tax`).

## What the API actually requires

From `onboarding-service` (read at design time, not assumed):

`EmployeeDeductionSetUpServiceImpl.setupEmployeeDeductions()` takes the deductions
file plus a deduction mapping file. The mapping file is the **same four-column
`DeductionMappingCsvDTO`** already used by `_Deductions_mapping.csv`:

```
Source Deduction Code, Source Deduction Code Name, Uzio Deduction Code, Uzio Deduction Code Name
```

The lookup is:

```java
DeductionMappingCsvDTO mapping = mappingBySourceName.get(csvRecord.getDeductionDesc());
```

and `ADPConfig.toPaycomDeductionRecord()` fills that field from the ADP file:

```java
paycom.setDeductionDesc(adp.getDeductionDescription());   // "DEDUCTION DESCRIPTION"
```

`DEDUCTION CODE` is **not** used for the lookup.

> `PaycomEmployeeDeductionRecordCsvDTO` is the shared internal record type for both
> vendors; the name is historical. ADP rows are parsed by
> `ADPEmployeeDeductionRecordCsvDTO` and converted into it. No Paycom logic runs.

### The two sides match with different strictness

| Side | Code | Behaviour |
|---|---|---|
| Source name | `mappingBySourceName.get(desc)` — plain `HashMap.get` | **case-sensitive, no trim** |
| Uzio name | `uzioDeductionName.trim().toLowerCase()` | case-insensitive, trimmed |

**Consequence:** `Source Deduction Code Name` must be copied **verbatim** from the
uploaded Voluntary Deduction file. Synthesising it from prior payroll headers
(`LTD POST TAX`) would fail every row. This is the same failure mode as the
`ROTH:MEMO : N` uppercase bug (2026-06).

Duplicate source names collapse via `Collectors.toMap(..., (first, second) -> first)`.

## Design

### Data flow

```
Voluntary Deduction file (new optional upload, top of page)
   │ drop rows with blank ASSOCIATE ID / DEDUCTION CODE / DEDUCTION DESCRIPTION
   │   (this removes ADP's "Report Totals:" footer generically)
   │ distinct DEDUCTION DESCRIPTION, verbatim, in first-appearance order
   ▼
exclusions (below)
   ▼
join into enriched_deds / skipped_deds from _render_deduction_setup_section
   │ 1. by Type Code, case-insensitive
   │ 2. else by base master  (master minus trailing " Pre-tax" / " After-tax")
   ▼
take that row's "UZIO Deduction Name"
   ▼
<safe_name>_EE_Deductions_mapping.csv   — 5th file in the existing download bundle
```

### Reading the file

`.csv` is read directly. For `.xlsx`, pick the first sheet whose columns include both
`DEDUCTION CODE` and `DEDUCTION DESCRIPTION` — the export ships a second
`Report Runtime Settings` sheet, and the data sheet name may vary by client. If no
sheet qualifies, or `ASSOCIATE ID` / `DEDUCTION CODE` / `DEDUCTION DESCRIPTION` is
missing, show an error naming the missing columns and emit no fifth file; the other
four downloads are unaffected.

All values are read as strings (`dtype=str`) so descriptions keep their exact
spelling and codes keep leading zeros.

### Why the join key is code + base master

Code alone fails for retirement deferrals: the Voluntary Deduction file carries
`88-ADP 401K%` / `87-ADP ROTH%` while the prior payroll carries `K1-ADP 401K` /
`6-ADP ROTH`. Both sides independently resolve to the `401k` / `Roth 401k` masters,
so matching on the base master joins them without an alias table. Verified: a
rename applied to `K1` in the UI flows through to the `88` row.

A client may legitimately run both a percent and a flat-dollar 401k. Each distinct
description gets its own CSV row; both point at the same Uzio name. The API keys on
description, so there is no collision.

### Why `UZIO Deduction Name` is copied, never recomputed

Re-running `map_adp_to_uzio_master()` on the Voluntary Deduction row would discard
the user's master-override dropdown and the empirical Pre/Post-tax verdict (the
Voluntary Deduction file has no tax-treatment column — the API sets
`taxTreatment(null)`). `_render_name_editor` mutates the row dicts in place and
`_render_deduction_setup_section` returns those same objects, so by the time the new
code runs the renames are already present. This is the existing contract used by
`_render_contribution_setup_section(results, enriched_deds)` and
`build_deductions_mapping_rows(enriched_deds, skipped_deds)`.

`skipped_deds` must be passed too, so UZIO defaults (`PAC-PAYACTIV` →
`Earned Wage Access`) resolve instead of reporting as unresolved.

### Exclusions

Deductions never assigned to employees during onboarding:

1. Resolved master in `{Child Support, Child Support 2, Spousal Support Order,
   Creditor Garnishment, Federal Tax Lien, State Tax Lien}` — covers Support,
   Garnishment (`73`, `93-GARNISHMENT%`) and Tax Levy.
2. Description matching `CHECKING` or `SAVINGS` on word boundaries — these are
   direct deposits (`CK1`/`CK2`/`CK3`/`SV1`), and they resolve to `<NEEDS REVIEW>`
   rather than a skippable master, so rule 1 does not catch them.

Excluded rows are listed on screen, not silently dropped.

### Conflicting duplicate descriptions

Rows are keyed by description, so two different codes sharing one description
collapse to a single CSV row. When they resolve to **different** Uzio names, that is
a genuine ambiguity the API would silently resolve by keeping whichever row came
first. Emit the first and surface an amber warning naming both codes and both
candidate names. On High Distinction this never fires — the only shared descriptions
(`SUPPORT` across `75`–`79`, `CHECKING` across `CK1`–`CK3`) are excluded first.

### Unresolved rows (approved: Option A)

A description that matches neither by code nor by base master was not in the prior
payroll, so the deduction does not exist in UZIO. Such rows are **omitted from the
CSV** and listed in a red on-screen warning naming the code and description.

Rejected alternatives: emitting a best-effort master can *succeed with the wrong
answer* — with no verdict available `map_adp_to_uzio_master` defaults to the
Pre-tax variant of a paired family, so a coin-flip `Critical Illness Pre-tax` would
silently assign the wrong tax variant to every employee if that master happened to
exist. Emitting a blank Uzio name only moves discovery to after the upload.

### UI

New optional `st.file_uploader` at the top of `render_ui()`, beside the existing
prior payroll uploader; accepts `.xlsx` and `.csv`. When a file is present, three
tables render after the deduction setup section: mapped, excluded (with reason),
unresolved (red). When absent, nothing changes anywhere.

### Output

`{safe_name}_EE_Deductions_mapping.csv`, appended to the existing `mapping_files`
list so one click still downloads everything. Built with `_mapping_csv_bytes()`
(plain UTF-8, no BOM). `Source Deduction Code` and `Uzio Deduction Code` are left
blank, matching the sample file and the other four mapping CSVs.

## Verification

Against the real High Distinction files:

- All 12 mappable descriptions resolve, matching the hand-built sample **12/12**,
  including `ADP 401K%` → `401k`, `ADP ROTH%` → `Roth 401k`,
  `ADP 401K LOAN` → `401(k) Loan`, and `LTD Post Tax` → `Voluntary LTD After-tax`
  (the last depends on the LTD code seed added 2026-08-19).
- Row order equals first-appearance order in the file, byte-identical to the sample.
- Excluded: `73`, `75`–`79`, `93`, `CK1`–`CK3`, `SV1`. Unresolved: none.
- Regression: with no Voluntary Deduction file uploaded, every existing output —
  the setup xlsx and all four mapping CSVs — must be byte-identical to before.

## Out of scope

- Paycom. Its Voluntary Deduction equivalent is a different export.
- Emitting a cleaned employee-deduction CSV for the API. The API parses CSV while
  the client file is `.xlsx`; converting it is a separate question.
- Employee-level validation (amount vs percent, employees absent from UZIO). The
  API validates and reports these itself.
