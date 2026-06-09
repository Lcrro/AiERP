# ERPNext Item Search Tool v0.1

`erpnext.search_items` is the Agent Runtime tool for finding standardized ERPNext `Item` records before creating or using material master data.

## Purpose

Use this tool before creating a new Item, selecting an Item for a procurement/sales/stock document, or resolving a user's informal material name.

The tool does not ask the LLM to guess one final material from thousands of names. It uses deterministic ERPNext queries plus local scoring rules, then returns candidates, scores, match reasons, and clarification questions.

## Tool

```json
{
  "tool": "erpnext.search_items",
  "arguments": {
    "query": "接头",
    "specs": {"model": "M36*2"},
    "item_group": "液压/高压管路",
    "enabled_only": true,
    "limit": 10
  }
}
```

## Parameters

| Name | Required | Meaning |
| --- | --- | --- |
| `query` | yes | User text, item code, standard name, alias, raw name, or generic material name. |
| `specs` | no | Structured specs extracted by the agent, such as `model`, `material`, `brand`, `standard`, `package_spec`. |
| `item_group` | no | Preferred ERPNext Item Group; matching candidates get a score boost. |
| `enabled_only` | no | Defaults to `true`; search queries exclude disabled items, while exact code matches may still be returned as disabled and not `ready`. |
| `limit` | no | Maximum candidates, default `10`. |

`query` remains required in the tool schema because the agent should normally pass the user's original phrase. Code-level handling tolerates an empty string for fallback cases; when `query` is empty, useful recall depends on structured `specs`.

## Result

The result data contains:

| Field | Meaning |
| --- | --- |
| `status` | `ready`, `needs_confirmation`, `needs_clarification`, or `not_found`. |
| `candidates` | Ranked item candidates with `item_code`, `item_name`, score, confidence, enabled state, and match reasons. |
| `questions` | Clarification or confirmation prompts for the agent to ask the user. |
| `decision_reason` | Short explanation for why the current status was chosen. |
| `warnings` | Non-fatal search issues, usually missing custom fields before item master setup. |
| `debug` | Diagnostic scoring data, including `top_score`, `second_score`, `score_gap`, `why_status`, and `warnings`. |

## Status Rules

| Status | Meaning |
| --- | --- |
| `ready` | A high-confidence candidate is clearly ahead and can be presented as the recommended match. |
| `needs_confirmation` | Candidates exist, but the agent should ask the user to confirm before selecting one. This includes disabled exact-code hits. |
| `needs_clarification` | The query is too broad, the top score is low, or the user needs to provide more specs. |
| `not_found` | No usable candidate was recalled. |

For generic names such as `接头`, `管`, `弯头`, or `电缆`, call the tool with extracted specs whenever possible:

```json
{
  "tool": "erpnext.search_items",
  "arguments": {
    "query": "接头",
    "specs": {"model": "M36*2"}
  }
}
```

With specs present, the tool can use those fields for recall and should ask for confirmation of the found candidate instead of simply saying the generic query is too broad.

v0.1 also performs light spec normalization for common shop-floor variants. For example, `M36*2`, `36×2`, and `36x2` can match the same threaded model, and `1.2` can match `1.2mm` for welding wire diameter.

## Agent Usage Rule

For new material creation, the sequence should be:

```text
search_items
  -> prepare_item_from_intent
  -> user confirmation
  -> create_item_from_intent
```

Do not let the LLM invent item codes or write raw `Item` documents directly.

## Setup Note

The best result quality requires running `erpnext.setup_item_master` first so custom Item fields such as `alias_names`, `raw_name`, `material`, `standard`, `brand`, `model`, `package_spec`, and `specification` exist in ERPNext.

If a custom field is missing, `erpnext.search_items` skips that field and records a warning instead of failing the whole search.

## Performance

v0.1 uses multiple deterministic ERPNext `search_documents` queries across item code, name, aliases, raw name, and selected spec fields. This is simple and transparent, but it can become chatty on large item masters.

v0.2 should consider a local/cache-backed item search index or a dedicated ERPNext endpoint that returns normalized searchable fields in one call.
