# Documentation Index

This project uses a lightweight documentation structure inspired by the Diataxis framework:

```text
overview      where to start and what exists
architecture  how the system is shaped
reference     precise API/schema/tool facts
planning      versioned work plans and checklists
operations    how to run, verify, and maintain local systems
```

The goal is to keep each document responsible for one kind of question.

## Start Here

- [Project README](../README.md): short project entrypoint.
- [Project Status](project-status.md): current branch, coverage counts, test status, and next queue.
- [Architecture Roadmap](architecture/roadmap.md): staged architecture goals.
- [Tool Layer v0.1 Checklist](planning/tool-layer-v0.1.md): current backend tool-layer work queue.
- [Item Master Search v0.1 Plan](planning/item-master-search-v0.1.md): material master and search work queue.

## Architecture

- [Architecture Roadmap](architecture/roadmap.md)
- [DocType Index And Agent Context](architecture/doctype-index.md)

Architecture docs explain how the system should be shaped and why.

## Planning

- [ERPNext Tool Layer v0.1](planning/tool-layer-v0.1.md)
- [ERPNext Tool Layer v0.2 Module Coverage](planning/tool-layer-v0.2-module-coverage.md)
- [Item Master Search v0.1](planning/item-master-search-v0.1.md)

Planning docs are versioned work queues. They should contain checklists, acceptance criteria, and the next task.

## Operations

- [Local Sandbox Operations](operations/local-sandbox.md)
- [Material Catalog PostgreSQL Operations](operations/material-catalog-postgres.md)

Operations docs explain how to run and verify local infrastructure.

## Reference

- [ERPNext Capability Map](reference/erpnext-capability-map.md)
- [Material Master Standard](reference/material-master-standard.md)
- [ERPNext Item Search Tool](reference/item-search-tool.md)
- [Purchase Material Standardization](reference/purchase-material-standardization.md)
- [Standard Item Catalog From Purchase Review](reference/standard-item-catalog-from-review.md)
- [Material Catalog PostgreSQL Layer](reference/material-catalog-postgres.md)
- [ToolCall Users & Permissions](reference/toolcall-users-permissions.md)
- [ToolCall Five Module Control Matrix](reference/toolcall-five-module-control-matrix.md)
- [ToolCall Assets](reference/toolcall-assets.md)
- [ToolCall Stock](reference/toolcall-stock.md)
- [ToolCall Buying](reference/toolcall-buying.md)
- [ToolCall Accounting](reference/toolcall-accounting.md)

Reference docs should be added when we have stable facts about schemas, tool contracts, or API behavior.

Planned reference docs:

```text
docs/reference/tool-contracts.md
docs/reference/agent-bridge-api.md
docs/reference/configuration.md
```

## Documentation Rules

- Keep the root `README.md` short.
- Put long architecture and design material under `docs/architecture/`.
- Put version-specific task lists under `docs/planning/`.
- Put runbooks under `docs/operations/`.
- Put stable schemas, tool contracts, and API details under `docs/reference/`.
- Do not commit generated caches, secrets, or live ERPNext business data.
- Prefer links over duplicated content.
