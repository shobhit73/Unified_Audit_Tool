# Onboarding census errors - what they mean and what fixes them

Seeded from real prod runs (1366, 1376, 1383, Sep 2026). **Append to this file after
every migration**: a reason that needed a subagent once should not need one again.

Buckets: `source-fix` we can correct the file - `uzio-setup` something must exist in
Uzio first - `client-data` only the client has the value - `transient` re-push those
employees, the data is fine.

## Errors - the record was skipped

| Reason (as logged) | Bucket | What it really means / fix |
|---|---|---|
| `Mandatory field 'SSN' is missing or empty.` | client-data | Blank in the source. Ask the client; do not invent a placeholder. |
| `Mandatory field 'Address Line 1' / 'City' / 'State' / 'Zipcode' for 'Primary Address' is missing or empty.` | client-data / source-fix | First check the source really is blank - on ADP files the home-zip column header is standardized to `Primary Address: Zip Code`, so a mapping slip can look like missing data. |
| `Mandatory field 'Job Title' is missing or empty.` | source-fix | Blank title that no auto-fix filled. Fill it from Department, or `Driver` for Non-Exempt Hourly, then make sure that title exists in the mapping. |
| `Job Title 'X' has an empty mapping value. This record will be skipped.` | source-fix | **The trap.** Either the mapping row is blank, or the title is not in the mapping at all - the message is identical for both. Remember the corrected file WRITES titles (Department value, or `Driver`); `titles_written_by_fixes()` lists them. Add the row and re-push. |
| `Invalid state for Primary Address zip code : 10952. Expected : NJ Found: NY` | source-fix + **human** | The zip and the state disagree. The API trusts the zip. Which one is wrong is a judgement call - ask before changing either. |
| `FLSA Classification (Exempt Status) 'null' is not a valid value. Allowed values are: Exempt, Non-Exempt` | source-fix | Blank FLSA that no rule could resolve. Driver/Walker/Helper titles are forced Non-Exempt + Hourly; anything else needs the real value. |
| `Zip code validation service error for '15797': No response body provided` | transient | A downstream zip service returned nothing. The data is fine - re-push those employees only. |
| `{"globalErrors":{},"fieldErrors":{"employee.emergencyContactDetails[0].name":...}}` (`API_ERROR`) | source-fix | An emergency-contact field failed the model's own validation - usually a blank name or unsupported characters. Read the fieldErrors key to see which field. |

## Warnings - the record went through, something was skipped

| Reason (as logged) | Bucket | What it really means / fix |
|---|---|---|
| `Reporting Manager ID 'X' not found. The reporting manager employee might not be onboarded yet.` | uzio-setup | The employee was created but has no manager linked. **Order matters**: onboard the managers first, then re-push the reportees (or set the manager by hand). Seen on run 1383 for 2 of 2 employees. |

## Things that are not errors but cost a migration anyway

- **The push answer only carries counts.** `FailureMap: 0` does not mean "nothing to
  look at" - run 1383 answered 0 failures and logged 2 warnings. Always read the run.
- **A job title that differs by one character** from Company Master is dropped
  silently - no error row at all. `python utils/check_job_titles.py` before pushing.
- **A big census gets no answer**: the request times out (or a gateway returns
  502/503/504) while Uzio keeps working - run 1376, 873 employees, 8 minutes. The run
  still exists; find it by FEIN + user + start time. Never assume it failed and push
  again.
