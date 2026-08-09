# Module Selection

Use `config/project_context.yaml` as the module index. Each active module lists its code paths, tests, and stable docs. Load only the entries needed for the request.

## Generated context

- `.runtime/context/project-snapshot.json`: Git status, configured entrypoints, and safe project state.
- `.runtime/context/repo-map.json`: compact files and top-level symbols grouped by active module.
- `.runtime/context/doc-audit.json`: Markdown classification and local link findings.

These files are local, generated, and ignored by Git. Regenerate them rather than editing them.

## Sensitive boundaries

Never read file contents below `.env`, `.secrets`, or runtime log/session directories. It is safe to report that these paths are excluded; it is not safe to include their contents in a snapshot or handoff.
