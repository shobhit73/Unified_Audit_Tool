# FIT/SIT Sanity — validate State Marital Status Description per state

**Date:** 2026-09-08
**Status:** Implemented
**Scope:** `apps/adp/fit_sit_sanity.py`, new `utils/state_filing_status.py`, new `utils/check_state_filing_status.py`. ADP only.

## Problem

The tool fills every blank `State Marital Status Description` with the literal string `"Single"`, with no reference to the employee's state:

```python
DEFAULTS = {
    "Dependents": "0",
    "Non-Resident Alien": "No",
    "State Marital Status Description": "Single",   # blind
}
```

`"Single"` is not universally valid. Missouri accepts only `Single or Married Spouse Works or Married Filing Separate`, `Married (Spouse does not work)` and `Head of Household`. Filling `"Single"` there produces a row the onboarding API rejects with *"Invalid State filing status: 'Single' for state: Missouri"*.

The same field is later compared by the withholding audit (`withholding_audit.py:100` maps `SIT_FILING_STATUS` → `State Marital Status Description`), so a wrong value also manufactures a mismatch downstream.

## Where the acceptance rules actually live

**Not** in `filing status_code.txt`. That file is the UI's display list, and reading it as the acceptance list overstates the problem badly — it suggests Iowa rejects `"Single"` when the API in fact accepts it.

The real table is `StateTaxWithholdingValidator.parseStateFilingStatus(stateCode, filingStatus)` in the onboarding service. It carries **33 states, 163 label aliases, 125 distinct enums** — several spellings map to one enum:

```java
case "IA":
    case "OTHER":
    case "SINGLE":
    case "OTHER (INCLUDING SINGLE)":
        return "IA_OTHER";
```

Matching is `stateFilingStatus.toUpperCase().trim()` — case-insensitive and trimmed, but **punctuation-sensitive**.

An unmatched value returns `null`, which `ADPStateTaxWithholdingValidator` writes straight back over the record:

```java
empRecord.setStateFilingStatusDesc(parsedStateFilingStatus);
```

### Three traps in reading that Java

The first transcription got 30 states, not 33, and the miss was silent:

- `case "HI" : // Hawaii` has a **space before the colon**. A `case\s+"([A-Z]{2})":` pattern skips it, so all six Hawaii labels folded into Georgia's block — Georgia appeared to accept `CERTIFIED DISABLED PERSON`, and Hawaii appeared to have no table at all.
- Nebraska uses a Java 14 multi-label case: `case "SINGLE", "MARRIED, AT SINGLE RATE":`. One label per line is the wrong assumption.
- Arizona returns percentages (`return "2.0";`), not `XX_ENUM` names, so a pattern anchored on the enum shape drops Arizona entirely. West Virginia was lost the same way.

The parser now anchors on the structure instead: a state case is one whose next line is `switch (upperFilingStatus)`. `utils/check_state_filing_status.py` carries the same parser and cross-checks that the label count it finds equals the count in the baked table, so a fourth quirk cannot pass unnoticed.

Georgia also has `case "":` mapping to `GA_SINGLE` — **a blank is genuinely accepted in Georgia**, and is left alone there rather than treated as missing.

`validateStateFilingStatus` then raises a row-level failure — *"… state filing status is missing"* when the source was blank, *"Invalid State filing status: 'X' for state: Y"* when it was unrecognised. So a bad value is a visible import failure for that employee, not a silent drop.

## Measured impact

Across all 30 FIT/SIT exports on this machine — 17,305 rows, measured by `scratch/verify_fit_sit_filing_status.py`:

| | rows |
|---|---|
| accepted as-is | 5463 |
| state absent from the API table (PA, OH, IL, MI, IN…) | 4364 |
| **rejected or blank — needs a human decision** | **6318** |
| no-SIT state (NV, TX…) | 1012 |
| **punctuation-only mismatch** | **114** |
| row has no worked-in state | 34 |

Only **18** distinct `(state, value)` pairs produce all 6318 rows. The worst single client file needs **6 dropdowns**; most need none.

Read the row totals as a scale, not a client count: the 30 files include both raw ADP exports and the corrected files the old tool already produced for the same clients, so a client with both is counted twice. The number that matters for the UI — 18 distinct pairs, 6 dropdowns worst case — is unaffected.

```
MO  Single                                     2850     UT  Married, but withhold at higher…    32
UT  (blank)                                    1966     AL  Single - Head of Household          32
MO  Single - Head of Household                  532     IA  Married - Two Incomes               20
WI  (blank)                                     244     AL  Married - Two Incomes                9
UT  Single                                      202     MS  Married                              5
MO  (blank)                                     132     MS  Married - Two Incomes                4
MO  Married                                     120     NM  (blank)                              3
UT  Married                                      62     MS  (blank)                              3
IA  Single - Head of Household                   56
MS  Single - Head of Household                   46
```

## Behaviour

Read the state from **`Worked in State Code`, and only that column** — it is what the API binds `worksInState` to:

```java
@CsvBindByName(column = "Worked in State Code")
private String worksInState;
```

There is deliberately no fallback to `State Tax Code`. The two disagree for multi-state employees, and classifying against a different state than the API will use would let the tool approve a value the API then rejects.

Then classify each row:

| Case | Action |
|---|---|
| Value accepted as-is | untouched |
| Punctuation-only difference | rewrite to the API's exact spelling |
| State absent from the API table | untouched |
| No-SIT state | untouched |
| Value rejected | user's dropdown choice |
| Blank, state has a table | user's dropdown choice (Georgia excepted — it accepts a blank) |
| Row has no state at all | untouched, listed on screen |

A row whose `Worked in State Code` is empty cannot be classified — there is no state to look up. Those rows are left exactly as they are and named on screen and in the Filing Status Review sheet, because guessing a state would mean guessing the answer. There are 34 such rows across the 17,305 scanned.

If `Worked in State Code` is missing from the uploaded file entirely, the filing-status work is skipped with a message saying so; `Dependents` and `Non-Resident Alien` are still filled as before, and the corrected file is still produced.

### Punctuation-only rewriting

ADP writes `Married, but withhold at higher single rate`. The API's WI and NM entries have no comma, so those rows fail; NY's entry *does* carry the comma, so NY passes. The API is inconsistent here, which is why matching ignores punctuation but the **written value is the API's exact spelling**. Leaving the source text in place would let the tool call a row fine that the API then rejects — 114 rows across the current client base.

Rewriting is safe because a de-punctuated match resolves to exactly one accepted label; it is a correction, not a guess.

### States left alone

For states the API's switch has no `case` for (PA, OH, IL, MI, IN, …) and for no-SIT states, no filing status can be valid, so there is nothing to map to. Values there are left exactly as they are: no complaint has come from those states, and it has not been verified whether the API even calls `validateStateFilingStatus` for them. Blanking 5308 rows to fix a problem that has not been observed would itself be a risk.

### The dropdowns

One dropdown per distinct `(state, value)` — not per row. Options are that state's accepted labels, which is what the API will convert to an enum.

The labels are offered, and written, in the API's own upper-case spelling (`SINGLE OR MARRIED SPOUSE WORKS OR MARRIED FILING SEPARATE`). The Java compares against `stateFilingStatus.toUpperCase()`, so that is literally the string it matches on. Title-casing it for looks would mangle `WIDOW(ER)` and `NRA`, and would put a value in the file that nobody has verified against the API.

**No option is pre-selected.** String similarity picks the wrong answer here: for NM `"Single"` the closest accepted label is `"Married but withhold as Single"` (0.33), when the correct answer is `"Single or Married filing separately"`. MO `"Single"` scores 0.19 against its correct target. A pre-filled wrong default is worse than an empty one, because it invites being accepted unread.

A dropdown left empty means those rows are **skipped** — neither filled nor altered — and listed on screen.

### Change Log

Every changed row gets a row in the existing `Change Log` sheet, carrying the old value and the reason:

```
State  Column                            Old Value   Filled With                     Reason
UT     State Marital Status Description  (blank)     SINGLE OR MARRIED FILING SEP…   Blank filled from your mapping (UT)
MO     State Marital Status Description  Single      SINGLE OR MARRIED SPOUSE WOR…   'Single' is not accepted for MO, remapped by you
WI     State Marital Status Description  Married, …  MARRIED BUT WITHHOLD AT HIGH…   Punctuation corrected to Uzio's spelling (WI)
```

A fourth sheet, **Filing Status Review**, carries one row per `(state, value)` pair with the employee count and what was decided — including the pairs left unmapped (`Still rejected by Uzio — no mapping chosen`) and the rows with no worked-in state. What was deliberately *not* done is on the record too.

No silent transformations — the same rule the census sanity tool follows.

## Out of scope

- `Dependents` → `0` and `Non-Resident Alien` → `No` keep their current blind defaults. Untouched.
- Paycom. Its FIT/SIT flow is separate.
- The withholding audit. It reads the same column but is not changed here.

## Files

| File | Responsibility |
|---|---|
| `utils/state_filing_status.py` (new) | The acceptance table (33 states, 163 aliases) baked in as data, plus `has_table`, `is_no_sit`, `accepted_labels`, `is_accepted`, `canonical_label`, `enum_for` |
| `utils/check_state_filing_status.py` (new) | Drift checker — re-parses `StateTaxWithholdingValidator.java` when present and exits non-zero if the baked table disagrees |
| `apps/adp/fit_sit_sanity.py` | Classification, the dropdown UI, applying choices, Change Log rows |

The table is baked rather than parsed at runtime because the Java file lives outside the repo and is not on every machine. That makes it a copy that can rot, which is what the checker is for — the same arrangement `utils/check_job_titles.py` uses for job titles, and for the same reason: a stale copy fails silently.

The checker prints the state, the label and both sides of any disagreement, and is a no-op with a clear message when the Java file is absent. It also guards one internal invariant: two labels of the same state may collapse to the same punctuation-free key (several states list a status with and without a comma), but only while both map to the same enum — otherwise the punctuation repair would be a coin flip.

## Verification

| Script | What it proves |
|---|---|
| `utils/check_state_filing_status.py` | the baked table still matches the Java, and is internally unambiguous |
| `scratch/verify_fit_sit_filing_status.py` | across all 30 client exports: every "accepted" row really resolves to an enum, every punctuation repair lands on an accepted label, and — with no mappings chosen — the corrected file differs from the pre-change tool's output *only* by no longer writing a blind `Single` |
| `scratch/verify_fit_sit_ui.py` | the Streamlit flow end to end through `AppTest`: nothing pre-selected, an unanswered dropdown skips its rows, and the results survive the rerun `st.download_button` triggers |

One thing the scan surfaced that is **not** part of this change: two client exports (`Happy Delivery`, `Travel Management`) are cp1252, not UTF-8, and `pd.read_csv` raises `UnicodeDecodeError` on them. That is pre-existing — the tool failed on those files before this change too — and needs the same strict-utf-8-then-cp1252 fallback the EE deduction mapping got.
