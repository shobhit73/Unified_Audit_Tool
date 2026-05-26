---
description: Pull the latest main into the current repo and rebase the current branch on it. Works in Unified_Audit_Tool, implementors_repo, or audit_fast_api.
---

You are executing the **/sync** workflow. The user wants their local clone of the current repo brought up to date with `main`, with their in-progress branch (if any) rebased on top. This is the "always pull before push" rule, automated. Run it at the start of every work session.

## Step 1 — Detect the repo

Run `git remote get-url origin`. Confirm it contains one of:
- `Unified_Audit_Tool` (root)
- `unified_audit_for_implementors` (implementors)
- `audit_fast_api_` (fastapi)

If not, stop and report — the command does not recognize this repo.

## Step 2 — Pre-flight checks

In parallel:
- `git status --short` — bail with a clear message if there are uncommitted or unstaged changes. Tell the user to commit (`/ship`) or stash first. Do NOT auto-stash.
- `git branch --show-current` — note which branch we are on.

## Step 3 — Sync

Two cases:

**Case A — on `main`:**
- `git fetch origin`
- `git pull --ff-only origin main`
- If `--ff-only` fails (local `main` has diverged), STOP and report. Do not auto-resolve. The user must investigate why their `main` has commits that aren't on origin.

**Case B — on a feature branch (anything not `main`):**
- `git fetch origin`
- `git rebase origin/main`
- If a conflict appears, STOP, list the conflicting files, and tell the user to resolve them manually (then `git rebase --continue`). Do not pick a side automatically.

## Step 4 — Report

Print a one-line summary:
- Which repo (by remote)
- Which branch
- Commits pulled / rebased on top
- Conflicts (if any) and what to do next

## Hard constraints

- NEVER use plain `git pull` (the merge form) — always `--ff-only` on `main` or `fetch + rebase` on a branch.
- NEVER use `--force`.
- NEVER touch other repos. /sync operates ONLY on the repo of the current working directory. Even if we are in root, do NOT recurse into `implementors_repo/` or `audit_fast_api/`.
- NEVER switch remotes to HTTPS.
- If the working tree is dirty, bail — do not auto-stash.
