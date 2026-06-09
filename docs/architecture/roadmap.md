# Architecture Roadmap

This roadmap describes the project by architecture stage.

Each stage answers one question:

```text
What should the system architecture be able to do at this point?
```

The roadmap should stay architecture-first. Product features can grow later, but every stage must make the system structure clearer and more capable.

## Stage 1: Natural Language ERPNext Loop

Architecture goal:

```text
User speaks naturally
  -> Agent translates intent into ToolCall
  -> System executes ToolCall
  -> ERPNext returns ToolResult
  -> Agent translates result back into natural language
```

This is the first complete running architecture.

Stage 1 is not about deep business optimization yet. It is about proving that a user can talk to an assistant, the assistant can produce structured ERPNext actions, the adapter can execute those actions, and the assistant can explain the ERPNext result back to the user.

Target architecture:

```text
User
  -> Chat / CLI / simple API entry
  -> Agent Runtime
  -> ToolCall
  -> ERPNext Adapter
  -> ERPNext / Frappe API
  -> ToolResult
  -> Agent Runtime
  -> Natural language answer
```

Core components:

- Chat or CLI entrypoint
- Agent Runtime
- Tool schema registry
- ToolCall schema
- ToolResult schema
- ERPNext Adapter
- ERPNext/Frappe HTTP client
- Basic `agent_bridge` Frappe app
- Basic execution log

What already exists:

- `ToolCall` and `ToolResult` schemas
- ERPNext Adapter
- ERPNext/Frappe HTTP client
- local ERPNext sandbox in WSL
- `agent_bridge` app installed on local ERPNext
- smoke tests for auth, customer query, and bridge ping

What is still missing:

- natural language input entrypoint
- Agent Runtime
- LLM tool selection
- conversion from user intent to valid `ToolCall`
- conversion from `ToolResult` to natural language answer
- basic conversation/session state

Stage 1 acceptance criteria:

- User can type a natural language request.
- Agent selects a valid ERPNext tool.
- Agent produces a structured `ToolCall`.
- Adapter executes the `ToolCall`.
- ERPNext returns real data or a real validation error.
- Result is represented as `ToolResult`.
- Agent explains the result in natural language.
- The whole loop runs from one command or endpoint.

Example target command:

```powershell
python scripts/chat_once.py --profile local "帮我查一个客户"
```

Example target response:

```text
我查到一个客户：Grant Plastics Ltd.
```

Important rule:

```text
The Agent Runtime may choose tools.
The Agent Runtime must not call ERPNext HTTP APIs directly.
Only the ERPNext Adapter talks to ERPNext/Frappe.
```

## Stage 2: Employee Context And Role Agent Layer

Architecture goal:

```text
Employee account
  -> user context
  -> role-aware assistant profile
  -> Agent Runtime
  -> ERPNext tools
```

Stage 2 adds the identity and role layer on top of the Stage 1 loop.

The system should know who the employee is, what role they have, and which assistant profile should guide the agent's behavior.

Target architecture additions:

- Employee/user context model
- ERPNext user mapping
- role-to-assistant registry
- assistant profiles
- role-specific tool hints
- role-specific DocType hints
- role-specific answer style

Example roles:

- Purchase
- Sales
- Warehouse
- Finance
- Technician
- Project Manager
- Company Manager
- General Employee

Acceptance criteria:

- A user can be mapped to an ERPNext account.
- The system can load a role-aware assistant profile.
- The same Agent Runtime can behave differently based on role context.
- The Stage 1 loop still runs unchanged underneath.

## Stage 3: ERPNext Knowledge And DocType Index Layer

Architecture goal:

```text
ERPNext metadata
  -> DocType index
  -> field/schema summaries
  -> Agent tool planning context
```

Stage 3 makes the agent aware of the structure of Nexterp/ERPNext instead of relying only on prompts and hardcoded examples.

Target architecture additions:

- DocType crawler/indexer
- DocType schema cache
- field summary generator
- child table mapping
- link field mapping
- required field detection
- submittable/workflow metadata
- report/method registry

Acceptance criteria:

- The system can list available DocTypes.
- The system can summarize important fields for a DocType.
- The agent can inspect schema before creating/updating documents.
- The agent can ask follow-up questions for missing required fields.
- Field debugging can be done through the index and live ERPNext metadata.

## Stage 4: Business Workflow Orchestration Layer

Architecture goal:

```text
User goal
  -> ActionPlan
  -> multiple ToolCalls
  -> intermediate ToolResults
  -> final business answer
```

Stage 4 turns single tool calls into multi-step ERP workflows.

Target architecture additions:

- ActionPlan schema
- multi-step planner
- intermediate state store
- follow-up question handling
- draft-first execution pattern
- workflow templates
- rollback/correction strategy where possible

Acceptance criteria:

- The agent can plan several ERPNext operations before executing.
- The agent can pause and ask for missing information.
- The agent can create drafts before high-impact operations.
- The Stage 1 ToolCall loop remains the execution unit.

## Stage 5: Proactive Agent Scheduler Layer

Architecture goal:

```text
Scheduled monitor
  -> Agent/Tool execution
  -> detected business event
  -> employee notification or suggested action
```

Stage 5 lets the system initiate work instead of only replying to user messages.

Target architecture additions:

- scheduled jobs
- saved monitors
- notification queue
- employee daily brief
- manager exception digest
- suggested action queue

Acceptance criteria:

- The system can run scheduled ERPNext checks.
- The system can produce role-specific reminders.
- A reminder can become a user-confirmed ToolCall.

## Stage 6: Supervisor Agent And Policy Layer

Architecture goal:

```text
Personal Agent ActionPlan / ToolCall
  -> Supervisor Agent / policy review
  -> allow / confirm / deny / escalate
  -> ERPNext Adapter execution
```

Stage 6 adds enterprise control as an independent layer.

Target architecture additions:

- policy engine
- supervisor agent
- risk classification
- action confirmation
- approval escalation
- audit dashboard
- immutable action log

Acceptance criteria:

- ToolCalls are auditable.
- High-risk actions can be intercepted.
- The supervisor layer is independent from the personal assistant.
- The system can explain why an action was allowed or blocked.

## Stage 7: Production Runtime Layer

Architecture goal:

```text
Reliable multi-user service
  -> secure credentials
  -> logs and monitoring
  -> retries and queues
  -> local and remote Nexterp support
```

Stage 7 hardens the system for real company usage.

Target architecture additions:

- secrets management
- per-user or delegated ERPNext identity
- rate limits
- structured logging
- retries and idempotency
- background worker queue
- deployment scripts
- monitoring
- staging/production profiles

Acceptance criteria:

- Local and remote Nexterp profiles work through the same adapter.
- No secrets are committed.
- Failed tool calls are visible and recoverable.
- The system can support multiple employee accounts.

## Immediate Next Architecture Target

Complete Stage 1.

The next code target is:

```text
scripts/chat_once.py
  -> accepts natural language
  -> invokes Agent Runtime
  -> gets ToolCall
  -> executes ERPNextAdapter
  -> sends ToolResult back to Agent Runtime
  -> prints natural language answer
```
