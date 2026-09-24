# ADP Time Off — fill blank Opening Balance for Hourly, and say so when nothing is written

**Date:** 2026-09-25
**Status:** Approved by Rohit
**Scope:** `apps/adp/timeoff_audit.py` only. ADP only.

## Problem

**1. Hourly employees lose real balances.** A blank Opening Balance in the UZIO template means "this policy is not assigned to this employee" (template rule 3), so the tool never fills it. That is right for someone who genuinely has no policy — but it silently drops balances ADP does have:

| Client | Blank rows | Hourly, with an ADP balance | Hours never imported |
|---|---|---|---|
| Moses | 8 | 2 — Jamal Jabouin, **Gadiel Soto** | 134.02 |
| High Distinction | 8 | 3 — Ryan Arkin, Alexis Crickon, Jayson DeCosta | 10.41 |
| Express | 0 | 0 | — |

**2. A run that writes nothing still looks successful.** With Express, an earlier upload had all 200 Opening Balances blank. The tool wrote zero balances and still showed the green *"Both files are ready — download them one at a time."* The only hint was a `Balances written: 0` counter among four; the 200 skipped rows were not on screen at all, only inside the audit workbook.

## Behaviour

### Filling blank rows

A new checkbox sits next to the Salaried one:

☑ **Fill blank Opening Balance for Hourly employees (assigns the policy in UZIO)** — **checked by default** (Rohit's call).

Unchecked, nothing changes. Checked, a blank row is filled only when **all** of these hold:

1. the template row's `Pay Type` is **not** Salaried,
2. an ADP policy is mapped to that row's UZIO policy,
3. that employee has a balance in it (a balance of **0.00 counts** — the policy is assigned with a zero balance).

A **Salaried** blank row is never filled, whatever the Salaried checkbox says. That checkbox governs Salaried rows which already carry a value; a blank one stays blank.

Filling a blank assigns a policy in UZIO, which changes the client's setup rather than just a number — so although the box is on by default, every filled row is counted on screen and named in the audit report, and the box can be cleared before generating.

### Audit report

Today every blank row lands in the **Unassigned Policies** sheet and in Exception Summary as `Unassigned Policy (Blank Balance)`. A row we fill is no longer unassigned, so it moves:

| Row | Today | After |
|---|---|---|
| Jamal Jabouin (Hourly) | Unassigned Policy | **`Blank filled — policy assigned (Paid PTO)`**, 20.65 |
| Gadiel Soto (Hourly) | Unassigned Policy | **`Blank filled — policy assigned (Paid PTO)`**, 113.37 |
| The other 6 (Salaried) | Unassigned Policy | unchanged |

So **Unassigned Policies** keeps only the rows left blank, and Exception Summary names, with amounts, exactly which employees will have a policy newly assigned in UZIO — the part worth reviewing before upload.

On screen, when any blank row is filled, a line says how many and that those employees will have the policy assigned.

### When nothing is written

If **no** balance was written, the green "ready" message is replaced by a red one that gives the reason, counting what stood in the way: rows left blank, Salaried rows skipped, UZIO policies with nothing mapped, ADP policies not imported, employees absent from the template.

Both downloads are still offered — the audit report is what explains the run.

The green message returns whenever at least one balance is written.

## Unchanged

- Blank still means "policy not assigned" whenever the new checkbox is off, which is the default.
- Salaried rows with a value, policy mapping, the census requirement, negative balances, file names, the two-file output.
## Also in this branch: balances now match ADP to the cent

ADP writes every transaction as `=ROUND(x, 2.0)` and prints, per employee and policy, a subtotal holding `round(sum of x)`. The tool evaluated each formula — rounding every transaction — and added afterwards, so the dropped fractions cost a cent whenever they added up: **281 of 2504** employee/policy totals across the client files on this machine sat 0.01 away from the client's own ADP report (Express: 126 of 643).

`_raw_amount()` now takes the number inside `=ROUND(...)` and `_sum_money` rounds once, the way ADP does. Afterwards every one of the 2501 single-record totals matches ADP exactly.

Three totals still differ by a cent, and should: there ADP holds **two employment records** for one Associate ID and prints two subtotals, each rounded on its own (6.83), while UZIO needs one figure for that person (6.84).

`scratch/verify_timeoff_rounding.py` checks both sides of that. The three older Time Off scripts compare against a pre-fix baseline, so their equality checks now allow a one-cent difference per row — and a policy's total, being a sum over everyone on it, up to a cent per employee.

## Verification

`scratch/verify_timeoff_blank_fill.py`, against the real client files:

| Case | Must hold |
|---|---|
| Checkbox off, all three clients | output identical to today, cell for cell (the old regression scripts run in this mode) |
| Moses, checkbox on | exactly 2 rows filled (20.65, 113.37); the 6 Salaried blanks untouched |
| High Distinction, checkbox on | exactly 3 rows filled (1.77, 1.70, 6.94); Salaried and no-balance blanks untouched |
| Express | unchanged either way — it has no blank rows |
| Audit | filled rows leave Unassigned Policies and appear as `Blank filled — policy assigned (…)` with their amount |
| Zero balance | an Hourly blank row whose ADP balance is 0.00 is filled with 0 |
| UI | the blank-row box starts checked and the Salaried one unchecked; an all-blank template is filled by default and the screen says how many; with the box cleared that same run writes nothing, shows a red message and no green one; a normal run still shows the green one |

The existing `scratch/verify_timeoff_policy_mapping.py` and `scratch/verify_timeoff_exception_status.py` must keep passing unchanged.
