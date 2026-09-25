---
name: census-migration
description: "End-to-end Amazon DSP census migration: sanity check, job title mapping, preflight against the real onboarding API rules, push to Uzio (only after the user says yes), read that run's log, triage every error into fix-here / Uzio-setup / ask-the-client, then fix and re-push. Trigger: /census-migration, census migrate karo, census push karo aur errors dekho, <client> ka census onboarding, push ke errors theek karo, run <id> ke errors fix karo."
user-invocable: true
---

# census-migration

Runs the whole census migration with the user, not for them. The push creates and
updates **real employee records in production**, so this skill is built around a
few places where it stops and asks.

Scripts live next to this file. `$SKILL` below is this directory; run them with the
repo's python from the repo root.

## The hard rules

1. **Never push without a yes in this conversation, for this exact file and FEIN.**
   Not a yes from earlier, not a yes for a different client, not "he said go ahead
   last time". `push_census.py` refuses unless `--confirm <FEIN>` is passed, and you
   only pass it after the user says yes to the summary you showed them.
2. **A second push is a new question.** Re-pushing after fixes needs its own yes.
3. **Never type the password.** Credentials come from the user's environment or
   `~/.uzio/onboarding-creds.json`, outside the repo. Never print or echo them.
4. **Never invent a job title mapping.** A title that is not in Company Master
   character-for-character makes the API skip that employee silently. See
   CLAUDE.md "Job titles must match Company Master".
5. **Subagents never push and never edit.** They read and report. Every decision
   that changes data or touches production happens in the main conversation,
   because a subagent cannot ask the user anything.
6. **Report in the user's language** (usually Hinglish), short, with tables. Never
   dump raw JSON at the user.

## Phase 1 - Sanity

Use the MCP census sanity tool for the vendor (`adp_census_sanity` /
`paycom_census_sanity`). Show the user, briefly: how many employees, what was fixed
automatically, what needs their attention, what is left blank.

Blockers (duplicate columns, missing required columns) stop everything - no file is
produced. Say so and stop.

## Phase 2 - Job title mapping

Build the mapping (`job_title_mapping` MCP tool). Then:

- `python utils/check_job_titles.py` - every title we offer must exist in Company
  Master. Exit 1 means drift; fix it before pushing.
- The mapping must also contain every title the **corrected** file writes, not just
  the ones in the original - blank job titles become the Department value or the
  literal `Driver`. `titles_written_by_fixes()` in `utils/job_title_mapper.py` is
  the list. A missing row here is the single most expensive mistake in this
  workflow: the employee is skipped with the same message a blank mapping gives.
- Ask the user to confirm the mapping table. Do not guess a title for them.

## Phase 3 - Preflight (subagents, read-only)

Before spending a production push, check the corrected file against the rules the
API actually enforces. Fan out `census-preflight` agents, one per area, in a single
message so they run together:

| Agent prompt covers | Looks at |
|---|---|
| Required fields | SSN, name, DOB, hire date, address, city, state, zip, job title |
| Job titles | mapping rows vs Company Master vs titles the fixes write |
| Addresses | zip vs state, 5-digit zips, unsupported characters |
| Employment | FLSA vs pay type, status/termination date, employment type |
| Emergency contacts | relationship values, special characters, blank names |

Give each agent the corrected census path, the mapping path, the vendor, and the
onboarding source path from CLAUDE.md. They return blockers and warnings with
employee IDs. Blockers get fixed before the push - that is the whole point of this
phase.

## Phase 4 - Push (STOP here)

Dry run first, always:

```
python "$SKILL/push_census.py" --fein <FEIN> --vendor <ADP|PAYCOM> \
    --census <corrected.csv> --mapping <mapping.csv> --dry-run
```

Show the user a short table: employer + FEIN, vendor, how many employees, which
files, and anything preflight flagged that they chose to leave. Then **ask**.

Only after an explicit yes, repeat the command with `--confirm <FEIN>` (same FEIN,
no `--dry-run`). The script pushes, then reads that run's log and prints a JSON
summary. It does not need babysitting: if the census is big enough that Uzio never
answers, the script finds the run by FEIN + user + start time (30-minute window).

If it says `still_running`, wait and re-read with `run_log.py --run <id> --wait 60`.
If it says the run was never found, the census most likely never reached Uzio -
tell the user, and do **not** push again on your own.

## Phase 5 - Triage the log

```
python "$SKILL/run_log.py" --run <id> --json --csv run_<id>_issues.csv
```

Read `references/error_catalog.md` first - most reasons are already in it. For every
reason that is **not** in the catalog, spawn one `census-error-triage` agent per
distinct reason (they run in parallel; cap at ~6 at a time). Each returns:

- which validator produced it, quoted from the onboarding source
- the bucket: `source-fix` (we can fix the file), `uzio-setup` (something must exist
  in Uzio first), `client-data` (only the client has the missing value)
- the exact column and value change, or what the user must do in Uzio
- whether it needs a human decision (ambiguous data, not a mechanical fix)

Merge their answers with the catalog and show the user one table: reason, how many
employees, bucket, what happens next. Then append the new reasons to
`references/error_catalog.md` so the next run is faster.

## Phase 6 - Fix and re-push (STOP again)

- `source-fix` - apply the corrections (`apply_data_corrections` MCP tool), re-run
  the sanity check, show the diff of what changed.
- `uzio-setup` - list exactly what to create in Uzio and in what order. Managers
  before their reportees: "Reporting Manager ID not found" only clears once the
  manager exists.
- `client-data` - write the list for the client. Nothing to do here until it comes
  back.

Only the employees that failed need to go again. Use the selective tools
(`selective_employee_extractor`, `adp_selective_census_sync`) rather than re-pushing
the whole file, and ask before that push too.

## When to stop and ask, even if not listed above

- The data is ambiguous (zip says NJ, state says NY - which one is right?).
- A fix would change what the data *means* (FLSA, pay type, status, salary), not
  just its format.
- Something in the log does not match anything in the catalog or the API source.
- The same push fails twice for the same reason.

## Files

- `push_census.py` - dry run, confirm, push, read the run log. Exit 0 clean, 1 errors
  logged, 2 not confirmed / usage, 3 API failure.
- `run_log.py` - read any run by id, or find it by FEIN + start time. `--json` for
  agents, `--csv` for the user.
- `references/error_catalog.md` - reason -> cause -> fix. Grows after every run.
- Both scripts import `utils/onboarding_core.py` from this repo, which is the same
  code the Streamlit app's "Push to Uzio" button uses. Fix bugs there, once.
