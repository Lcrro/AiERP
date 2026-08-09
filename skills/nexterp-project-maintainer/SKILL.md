---
name: nexterp-project-maintainer
description: Maintain the Nexterp repository context, project status, documentation boundaries, handoff snapshots, and safe cross-machine development workflow. Use when starting or handing off Nexterp work, reorganizing project docs, checking repository health, generating compact context, or installing the project maintenance workflow.
---

# Nexterp Project Maintainer

Use the repository as the source of truth; do not rely on a long Codex conversation.

## Start a task

1. Run `python scripts/dev/project_context.py resume`.
2. Check `git status --short` and preserve all user changes.
3. Select only the module(s) named by the request. Read their configured paths, tests, and docs; do not scan the whole repository.
4. Prefer CodeGraph for dependency questions. If unavailable, use `rg` and then `.runtime/context/repo-map.json` after `snapshot`.

## Finish a milestone

1. Run focused tests, then `python scripts/dev/project_context.py snapshot` and `audit-docs`.
2. Run `python scripts/dev/project_context.py check`.
3. At a milestone boundary, run `checkpoint --write` and `handoff --write`.
4. Commit only reviewed source, tests, docs, and configuration. Never commit `.env`, `.secrets`, credentials, ERPNext business data, or runtime logs.

## Boundaries

- ERPNext remains the authority for permissions, workflows, inventory, and documents.
- Writes use the employee identity, explicit confirmation, idempotent request IDs, and post-write readback.
- Do not turn chat history, generated snapshots, or runtime logs into project facts.
- `project_context.yaml` stores durable status; Git derives branch, HEAD, worktree, and commit facts.

For module selection and the generated context files, read [references/module-selection.md](references/module-selection.md) only when needed.
