# Agent Notes

## Local Codex Environment

- Current project path on Windows:
  - `C:\Users\Administrator\Documents\nexterp agent 2`
- The user changed Codex settings back to:
  - Agent environment: Windows native
  - Integrated terminal shell: WSL
- Do not ask the user to switch the whole Agent environment to WSL again just to fix shell issues. When they tried that, the existing conversation/history appeared to disappear because Codex treated it like a different environment context.
- Windows sandbox PowerShell may fail with:
  - `CreateProcessWithLogonW failed: 1326`
- Treat that as a Codex/Windows process-launch issue, not a project bug.
- Prefer WSL-compatible shell commands when possible.
- If using WSL paths, convert:
  - Windows: `C:\Users\Administrator\Documents\nexterp agent 2`
  - WSL: `/mnt/c/Users/Administrator/Documents/nexterp agent 2`

## Escalation And Safety

- Avoid requesting broad approval for arbitrary PowerShell or Python commands.
- If a simple read command fails due to the Windows sandbox, try a WSL-safe command before asking the user to change settings.
- Do not use destructive commands such as `git reset --hard`, `git checkout --`, or recursive delete unless the user explicitly asks.
- Use `apply_patch` for manual file edits.
