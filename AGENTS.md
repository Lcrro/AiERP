# Nexterp Engineering Rules

## Start and finish

- Start a task with `python scripts/dev/project_context.py resume`.
- Check `git status --short` before edits and keep user changes intact.
- Work on the smallest relevant module set; read its configured code, tests, and docs only.
- At a milestone boundary run focused tests, `project_context.py check`, then `checkpoint --write` and `handoff --write`.

## Architecture boundaries

- ERPNext is the authority for permissions, workflows, inventory, documents, and business state.
- OpenClaw and DeepSeek understand requests and plan; Nexterp resolves entities, validates fields, freezes writes, and executes through the employee identity.
- Every write requires explicit confirmation, an idempotent request ID, and post-write readback.
- Never let a model provide employee identity, ERPNext credentials, or arbitrary low-level ToolCall parameters.

## Safety and data

- Never commit or package `.env`, `.secrets`, credentials, ERPNext database dumps, real business documents, or `data/runtime/` logs and sessions.
- Do not use destructive Git commands to discard user changes.
- Generated context under `.runtime/context/` is local and ignored; regenerate it instead of editing it.

## Tests

```powershell
python -m pytest tests/unit/item_master -q
python -m pytest -q -m "not integration and not llm and not erpnext_write and not slow"
python -m pytest -q
python scripts/dev/project_context.py check
```

Integration, LLM, and ERPNext write tests require explicit local configuration and should run only at milestone boundaries.
