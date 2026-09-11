# ADP Time Off — map ADP policies to UZIO policies

**Date:** 2026-09-11
**Status:** Design approved, awaiting spec review
**Branch:** `rohit/adp-timeoff-exception-status` (same branch as the Exception Summary status/date columns)
**Scope:** `apps/adp/timeoff_audit.py` only. ADP only.

## Problem

The tool never reads ADP's `POLICY NAME`. It adds every ADP policy an employee has into one number and writes that number into **every** template row the employee has, whatever that row's `Time Off Policy Name` says.

For a client with one policy on each side (Express, FlashHUB, Innovdel, Lazo, North Star, First Line — all `Amazon PTO` → `Paid PTO`), that happens to be right. For anyone else it is wrong, and Moses shows how badly:

| | ADP | UZIO template |
|---|---|---|
| Policies | `PTO` only (plus one `Salary  PTO`) | two rows per employee: `NY State Prenatal Leave` (20.0 each) and `Paid PTO` |

The tool wrote each employee's PTO total into **both** rows. 93 of 96 prenatal rows changed from 20.0 to the PTO figure — up to 120, down to 0. Template rule 5 says an uploaded balance replaces the existing one, so uploading that file would have overwritten 93 employees' prenatal leave. Blanking the rows is no escape: rule 4 deactivates a policy whose balance is left blank.

Hansen Brothers (79 of 100 employees on three ADP policies) and High Distinction (two employees on `Salaried Time Off Policy` + `Salaried Sick Time Policy`) have the same shape.

## Behaviour

### 1. The mapping step

After the three files are uploaded, the tool reads the ADP balance summary and the UZIO template and shows a **Policy Mapping** section before Generate:

- one row per distinct ADP `POLICY NAME`, showing the employee count and total balance
- a dropdown per row: every distinct `Time Off Policy Name` in the template, plus **Do not import**

### 2. Auto-mapping (user can change it)

An ADP policy whose name contains the word `PTO` or the phrase `Paid Time Off` (case-insensitive) is pre-set to the template's PTO policy:

- the template policy named exactly `Paid PTO` (case-insensitive, trimmed), if there is one
- otherwise the single template policy containing the word `PTO`, if there is exactly one
- otherwise nothing — the dropdown starts on **Do not import**

Every other ADP policy starts on **Do not import**.

| Client | ADP policy | Starts on |
|---|---|---|
| Moses | `PTO`, `Salary  PTO` | Paid PTO |
| Express, High Distinction | `Amazon PTO` | Paid PTO |
| High Distinction | `Salaried Time Off Policy`, `Salaried Sick Time Policy` | Do not import |
| Hansen Brothers | `New York City Unpaid Leave`, `New York City Prenatal Leave` | Do not import |

Only PTO is guessed. A wrong guess on a leave policy would move hours into the wrong bucket, and it would look plausible enough to be accepted unread.

### 3. The salaried checkbox

☐ **Fill balances for Salaried employees too** — unchecked by default.

"Salaried" means the template row's **`Pay Type`** is `Salaried`. It is UZIO's Pay Type, not the ADP policy name, that decides: at High Distinction the two holders of ADP's `Salaried …` policies are `Hourly` in UZIO.

Unchecked, a Salaried employee's rows are left exactly as the template has them. Checked, they are filled like everyone else.

This changes today's output for clients with Salaried employees on a filled PTO row: Express has 9, which the tool fills today and will not by default.

If the template has no `Pay Type` column, nobody is treated as Salaried and the screen says so.

### 4. Filling each template row

For template row (employee E, UZIO policy P):

| Case | Result |
|---|---|
| No ADP policy is mapped to P (Moses's prenatal rows) | untouched |
| Opening Balance blank in the template (policy not assigned) | untouched — the existing rule |
| Pay Type `Salaried` and the checkbox is off | untouched |
| E has no balance in any ADP policy mapped to P | untouched |
| otherwise | **sum** of E's balances across every ADP policy mapped to P |

Several ADP policies mapped to one UZIO policy are added together (Moses: `PTO` + `Salary  PTO` → Paid PTO).

Sums keep today's money handling — `min_count=1` so an unreadable amount stays empty rather than becoming 0.00, then rounded to cents — and additionally turn a `-0.0` into `0.0`, so a balance that nets to zero is never written as `-0`.

## Audit report

### "ADP Balance" everywhere means mapped policies only

In **Balance vs UZIO Status** and **Exception Summary**, an employee's ADP Balance is the sum of their balances in *mapped* ADP policies. A policy set to Do not import contributes nothing.

"Missing in Uzio Template" generalises to: E has a balance in an ADP policy mapped to P, but the template has no (E, P) row. For a one-policy client that is exactly today's meaning.

### New sheet: Policy Mapping

One row per ADP policy, and one row per UZIO policy nothing was mapped to:

| ADP Policy | Mapped To | Employees | Total ADP Balance | Set By |
|---|---|---|---|---|
| PTO | Paid PTO | 204 | 5056.63 | Auto |
| Salary  PTO | Paid PTO | 1 | 0.00 | Auto |
| (none) | NY State Prenatal Leave | — | — | Not filled |

`Set By` is `Auto` when the user left the suggestion as it was, `You` when they changed it.

### Exception Summary — two new issue categories

Same six columns as today (Employee ID, Employee Name, Employment Status, Termination Date, Issue Category, ADP Balance). The policy name goes in the category text:

- **`Salaried — not filled (<UZIO policy>)`** — one row per template row skipped *only* because of the checkbox: the row was assigned, E is Salaried, and E has a mapped balance for it. ADP Balance = the amount that would have been written.
- **`ADP policy not imported (<ADP policy>)`** — one row per employee per Do-not-import policy with a **non-zero** balance. ADP Balance = that policy's balance. Zero balances are left out; they carry nothing to lose.

## Screen

- The four counters stay; **Balances written** counts rows actually written.
- Under them, before the downloads, a short list of anything left out: Salaried rows skipped, ADP policies not imported with their total hours, UZIO policies nothing was mapped to. No silent transformations.
- Changing a mapping or the checkbox after Generate discards the previous result, the same way a new upload already does — so a download always matches what is on screen.

## Unchanged

- The census stays mandatory; Employment Status / Termination Date stay on Exception Summary.
- Blank Opening Balance still means "policy not assigned" and is never filled.
- Negative balances are written as they are.
- Unassigned Policies sheet, file names, two-file output, row-4 headers.

## Out of scope

- Paycom's Time Off tool.
- `audit_fast_api` / MCP.
- Mapping memory across runs — every run starts from the auto-mapping.

## Verification

`scratch/verify_timeoff_policy_mapping.py`, on real files:

| Case | Must hold |
|---|---|
| Moses | all 96 prenatal rows stay 20.0; the 86 assigned Hourly Paid PTO rows equal ADP PTO; Salaried rows untouched; Policy Mapping shows `Salary  PTO` → Paid PTO (its one holder's Paid PTO row is blank and Salaried, so no cell changes for it) |
| Express, checkbox **on** | filled template identical, cell for cell, to today's output — the regression guarantee for one-policy clients |
| Express, checkbox **off** | every row that differs from today's output is one of the 9 Salaried rows (a Salaried row whose ADP balance is 0 does not differ); all 9 are listed under `Salaried — not filled` |
| High Distinction | the two `Salaried …` policies start on Do not import and appear under `ADP policy not imported` wherever their balance is non-zero |
| UI (AppTest) | mapping rows and defaults render; the checkbox starts unchecked; changing a mapping after Generate discards the previous downloads |
