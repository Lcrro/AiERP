import { Type } from "typebox";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import type { OpenClawPluginDefinition } from "openclaw/plugin-sdk/core";

import {
  capabilityRequest,
  isPreviewOnlySession,
  isWorkbenchSession,
  trustedIdentity,
  type PluginConfig,
} from "./client.js";

function toolResult(payload: Record<string, unknown>) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(payload, null, 2) }],
    details: payload,
  };
}

const plugin: OpenClawPluginDefinition = definePluginEntry({
  id: "nexterp-capability",
  name: "Nexterp Capability Manual",
  description: "Progressive Nexterp guides with frozen ERPNext operations.",
  register(api) {
    api.registerTool((ctx) => {
      const identity = trustedIdentity(ctx);
      const config = (ctx.config?.plugins?.entries?.["nexterp-capability"]?.config ?? {}) as PluginConfig;
      const tools = [
        {
          name: "nexterp_search_capabilities",
          label: "Search Nexterp capabilities",
          description: "Search the authorized Nexterp business capability catalog in Chinese. Call this before loading a guide.",
          parameters: Type.Object({
            query: Type.String({ minLength: 1, maxLength: 500, description: "Business goal in concise Chinese." }),
            module: Type.Optional(Type.String({ maxLength: 60 })),
          }, { additionalProperties: false }),
          async execute(_id: string, rawParams: unknown) {
            const params = rawParams as { query: string; module?: string };
            return toolResult(await capabilityRequest("/api/capabilities/search", identity, { body: params, config }));
          },
        },
        {
          name: "nexterp_load_guide",
          label: "Load Nexterp guide",
          description: "Load one to three selected capability nodes, their guide, and only the next adjacent nodes.",
          parameters: Type.Object({
            node_ids: Type.Array(Type.String(), { minItems: 1, maxItems: 3 }),
          }, { additionalProperties: false }),
          async execute(_id: string, rawParams: unknown) {
            const params = rawParams as { node_ids: string[] };
            return toolResult(await capabilityRequest("/api/guides/load", identity, { body: params, config }));
          },
        },
        {
          name: "nexterp_prepare_operation",
          label: "Prepare Nexterp operation",
          description: "Submit business facts for deterministic resolution and compilation. It never writes ERPNext.",
          parameters: Type.Object({
            operation_id: Type.String({ pattern: "^op\\.[a-z0-9_.]+$" }),
            request_id: Type.String({ minLength: 1, maxLength: 180 }),
            project: Type.Optional(Type.String()),
            warehouse: Type.Optional(Type.String()),
            schedule_date: Type.Optional(Type.String({ description: "ISO date YYYY-MM-DD when known." })),
            schedule_text: Type.Optional(Type.String({ description: "Relative Chinese date such as 明天 or 后天." })),
            posting_date: Type.Optional(Type.String({ description: "Posting date in ISO YYYY-MM-DD." })),
            valid_till: Type.Optional(Type.String({ description: "Quotation validity date in ISO YYYY-MM-DD." })),
            currency: Type.Optional(Type.String()),
            message: Type.Optional(Type.String({ maxLength: 4000 })),
            supplier: Type.Optional(Type.String({ description: "One supplier name as spoken by the user; Nexterp resolves it." })),
            suppliers: Type.Optional(Type.Array(Type.String(), { maxItems: 50 })),
            source_documents: Type.Optional(Type.Array(Type.Object({
              doctype: Type.String({ minLength: 1 }),
              name: Type.String({ minLength: 1 }),
            }, { additionalProperties: false }), { maxItems: 20 })),
            items: Type.Optional(Type.Array(Type.Object({
              raw_item_text: Type.Optional(Type.String()),
              item_code: Type.Optional(Type.String()),
              source_row: Type.Optional(Type.String({ description: "ERPNext child-row name returned by the source document." })),
              qty: Type.Optional(Type.Number({ exclusiveMinimum: 0 })),
              uom: Type.Optional(Type.String()),
              rate: Type.Optional(Type.Number({ minimum: 0 })),
              warehouse: Type.Optional(Type.String()),
              project: Type.Optional(Type.String()),
              schedule_date: Type.Optional(Type.String()),
              reason: Type.Optional(Type.String({ maxLength: 500 })),
            }, { additionalProperties: false }), { maxItems: 100 })),
            full_return: Type.Optional(Type.Boolean()),
          }, { additionalProperties: false }),
          async execute(_id: string, rawParams: unknown) {
            const params = rawParams as Record<string, unknown>;
            return toolResult(await capabilityRequest("/api/operations/prepare", identity, { body: params, config }));
          },
        },
        ...(!isWorkbenchSession(identity.sessionKey) ? [{
          name: "nexterp_execute_prepared_operation",
          label: "Execute prepared Nexterp operation",
          description: "Execute one immutable pending operation after OpenClaw obtains explicit user approval.",
          parameters: Type.Object({
            pending_id: Type.String({ minLength: 1, maxLength: 80 }),
          }, { additionalProperties: false }),
          async execute(_id: string, rawParams: unknown) {
            if (isPreviewOnlySession(identity.sessionKey)) {
              throw new Error("A/B 对比会话只允许预览，不能执行 ERPNext 写入");
            }
            const params = rawParams as { pending_id: string };
            return toolResult(await capabilityRequest("/api/operations/execute", identity, { body: params, config }));
          },
        }] : []),
      ];
      return tools;
    }, {
      names: [
        "nexterp_search_capabilities",
        "nexterp_load_guide",
        "nexterp_prepare_operation",
        "nexterp_execute_prepared_operation",
      ],
    });

    api.on(
      "before_tool_call",
      async (event, ctx) => {
        if (event.toolName !== "nexterp_execute_prepared_operation") {
          return;
        }
        const pendingId = typeof event.params.pending_id === "string" ? event.params.pending_id : "";
        if (!pendingId) {
          return { block: true, blockReason: "pending_id is required" };
        }
        if (ctx.sessionKey && isPreviewOnlySession(ctx.sessionKey)) {
          return { block: true, blockReason: "A/B 对比会话只允许预览，不能执行 ERPNext 写入" };
        }
        const hookContext = ctx as typeof ctx & {
          requester?: { senderId?: string };
          pluginConfig?: PluginConfig;
          abortSignal?: AbortSignal;
        };
        const externalSubject = hookContext.requester?.senderId ?? process.env.NEXTERP_OPENCLAW_DEV_SUBJECT;
        if (!externalSubject || !ctx.sessionKey) {
          return { block: true, blockReason: "Trusted requester or session identity unavailable" };
        }
        const identity = { externalSubject, agentId: ctx.agentId ?? "", sessionKey: ctx.sessionKey };
        const pluginConfig = hookContext.pluginConfig ?? {};
        const pending = await capabilityRequest(`/api/operations/${encodeURIComponent(pendingId)}`, identity, {
          method: "GET",
          config: pluginConfig,
          signal: hookContext.abortSignal,
        });
        const summary = pending.summary as Record<string, unknown> | undefined;
        return {
          requireApproval: {
            title: String(summary?.title ?? "执行 Nexterp 业务操作"),
            description: JSON.stringify(summary ?? { pending_id: pendingId }, null, 2),
            severity: "warning" as const,
            timeoutMs: 120_000,
            allowedDecisions: ["allow-once", "deny"] as Array<"allow-once" | "deny">,
          },
        };
      },
      { priority: 100, matcher: ["nexterp_execute_prepared_operation"], timeoutMs: 15_000 } as never,
    );
  },
});

export default plugin;
