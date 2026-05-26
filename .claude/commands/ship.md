---
description: Commit current work, auto-mirror to sibling repos if needed, push via SSH, and open a PR. Works in Unified_Audit_Tool, implementors_repo, or audit_fast_api.
---

You are executing the **/ship** workflow. The user wants their current changes shipped to `main` via a PR with ALL the project-specific mirror logic handled automatically. The user does NOT want to be asked questions unless something is genuinely ambiguous — Claude handles everything. Branch naming, commit messages, mirror copies, multi-repo pushes, and PR creation are all your responsibility.

Run these steps in order. Use parallel tool calls when steps are independent.

## Step 1 — Detect which repo we are in

Run `git remote get-url origin` in the current working directory. Match the URL:

- Contains `Unified_Audit_Tool` → **ROOT repo**. Mirror logic applies (see Step 5).
- Contains `unified_audit_for_implementors` → **IMPLEMENTORS repo**. No mirroring (this IS a mirror destination).
- Contains `audit_fast_api_` → **FASTAPI repo**. No mirroring.

If the remote matches none of these, stop and tell the user the command does not recognize this repo. Do not improvise.

## Step 2 — Inspect the changes

In parallel:
- `git status` — see what changed.
- `git diff` — see the actual content of the changes.
- `git diff --cached` — see anything already staged.
- `git log -5 --oneline` — match this repo's commit-message style.
- `git branch --show-current` — note the current branch.

If there are zero changes (staged or unstaged) and we are not on an unpushed branch, stop and report "nothing to ship."

Derive a short kebab-case slug describing the change (e.g. `fix-flsa-driver-rule`, `add-suta-per-state`, `update-disclaimer-text`). Keep it under 40 chars.

## Step 3 — Branch handling

- If currently on `main`: create a new branch `<user>/<slug>` (use the git user's first name, lowercase) and switch to it. NEVER commit directly to `main`.
- If already on a feature branch (anything not `main`): stay on it.

## Step 4 — Commit

- Stage only the files that actually changed (use explicit `git add <file>` per file — do NOT use `git add -A` or `git add .`, to protect against accidentally committing secrets or junk).
- Skip anything that looks like a secret (`.env`, `credentials.*`, `*.pem`, `*.key`).
- Write a concise commit message (1–2 sentences, why-focused, matching recent commit style from `git log`).
- Append the Co-Authored-By trailer per the standard commit protocol.
- Use a HEREDOC for the commit message to preserve formatting.

## Step 5 — Mirror (ROOT repo only — skip entirely if Step 1 detected implementors or fastapi)

Determine which mirrors are needed by looking at the files changed in Step 4.

### 5a. Mirror to `implementors_repo/` — BLIND BYTE-IDENTICAL COPY

CLAUDE.md is explicit: `implementors_repo/` is a FULL MIRROR (not a slim fork) of `app.py`, `apps/`, `utils/`. Pushing only to root silently breaks the implementors Streamlit Cloud deploy.

If any of these files changed in root, mirror them:
- Any file under `apps/**`
- `app.py`
- Any file under `utils/**` (`audit_utils.py`, `ui_components.py`, `preprocess_source_data.py`, `withholding_core.py`)
- `key_mapping.yml`
- `templates/Uzio_Census_Template.xlsm`

Procedure:
1. Copy each changed file from root into `implementors_repo/<same relative path>`, overwriting.
2. `cd implementors_repo/` (use absolute path for safety).
3. Create or check out the same `<user>/<slug>` branch as in the root repo.
4. Stage the copied files (explicit per-file `git add`).
5. Commit with the same message as the root commit, but append `(mirror)` to the subject.
6. Push to its remote (the one whose URL contains `unified_audit_for_implementors`) over SSH.
7. Open a PR via `gh pr create` with title prefixed `[mirror]` and a body noting this mirrors PR #N from the root repo (fill in once you have the root PR number).

### 5b. Port to `audit_fast_api/` — NOT a blind copy

CLAUDE.md is explicit: "the latter has its own slimmed `core/` port — apply the equivalent fix, don't blind-copy."

Trigger: any change in root to `utils/audit_utils.py`. If `utils/audit_utils.py` did NOT change, skip 5b entirely.

Procedure:
1. Read the structure of `audit_fast_api/` (look for `core/` and `utils/` subdirectories).
2. Identify the function(s) you changed in root's `utils/audit_utils.py`.
3. Find the equivalent function(s) in `audit_fast_api/` (likely under `core/census/` or `audit_fast_api/utils/audit_utils.py`).
4. Read both files. Apply the **semantically equivalent** change to the fastapi side — do not blind-overwrite, because the fastapi version is structurally different.
5. `cd audit_fast_api/`, create/check out `<user>/<slug>` branch, commit with the same message + `(port)` suffix, push to its SSH remote, open a PR via `gh pr create` with title prefixed `[port]`.

If the equivalent fix in fastapi is non-trivial or ambiguous, stop and ask the user before guessing — porting silently broken code is worse than asking.

## Step 6 — Push the original repo's branch

Push the current branch (the root repo's branch if we were in root, or whichever single repo we were in) to its remote over SSH.

- The remotes are already SSH. Do NOT modify them. Do NOT switch to HTTPS — corporate TLS inspection breaks HTTPS git on this machine.
- Use `git push -u origin <branch>` the first time, plain `git push` after.
- If push is rejected, STOP and report. Do not `--force`. Do not `--no-verify`.

## Step 7 — Open the PR for the originating repo

If multiple `gh` accounts are logged in (check `gh auth status`), the active one may not have collaborator access to the current repo's owner. Before `gh pr create`:

1. Extract the owner from `git remote get-url origin` (the segment between `github.com:` and `/`, e.g. `shobhit73` for `git@github.com:shobhit73/Unified_Audit_Tool.git`).
2. Run `gh auth switch -u <owner>` — ignore any error from this (the account may not exist, in which case keep whichever account is already active).
3. Then run `gh pr create`. If it fails with "must be a collaborator", try `gh auth switch` to the other account and retry once.

Use `gh pr create` with:
- Title under 70 chars, why-focused.
- Body with `## Summary` (1–3 bullets) and `## Test plan` (checklist) sections.
- Footer: `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- Pass the body via HEREDOC for correct formatting.

Print every PR URL (root + mirror + port, whichever apply).

## Step 8 — Auto-merge each PR and sync local main

For every PR created in this run (root + mirror + port, whichever apply):

1. `gh pr merge <PR-number-or-URL> --squash --delete-branch` (run from inside the matching repo, with the matching active gh account from Step 7).
2. If the merge is rejected because the PR has merge conflicts with `main`, STOP and report — do not improvise (do not `--admin`, do not force).
3. After all merges succeed, in each affected repo, run `git checkout main && git pull --ff-only origin main` to bring the local clone up to date.
4. Delete the local feature branch with `git branch -d <branch>` (the `-d` form, never `-D` — if git refuses because the branch isn't merged locally, stop and report).

Note for the user: this auto-merges without a code-review pause. Future PRs from this command land on `main` immediately. This is acceptable because the alternative the user is moving away from is direct-to-main pushes — auto-merged PRs are strictly better (branch history, revertable, mirror-safety enforced). If a collaborator review step becomes needed later, remove this Step 8 and switch to manual merges.

## Hard constraints — do not violate

- NEVER push directly to `main` (any of the three repos).
- NEVER use `--force`, `--force-with-lease`, `--no-verify`, `--no-gpg-sign`, or `-i` interactive flags unless the user explicitly asks in this conversation.
- NEVER switch any remote from SSH to HTTPS.
- NEVER use `git add -A` or `git add .` — always stage explicit files.
- NEVER commit files that look like secrets.
- If anything fails (push rejection, merge conflict, missing `gh` auth, etc.), STOP and report what happened. Do not improvise destructive recovery.
- Do not amend existing commits — always create new commits.

## Output format

When done, print a compact summary:
- Which repo(s) you pushed to
- Branch name(s)
- PR URL(s)
- Anything skipped and why (e.g. "no `audit_fast_api/` port needed — `utils/audit_utils.py` was not modified")
