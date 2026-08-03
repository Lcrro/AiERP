export type TrustedToolIdentity = {
  externalSubject: string;
  agentId: string;
  sessionKey: string;
};

export type PluginConfig = {
  baseUrl?: string;
  requestTimeoutMs?: number;
};

export function isPreviewOnlySession(sessionKey: string): boolean {
  return sessionKey.includes(":compare-preview:");
}

export function isWorkbenchSession(sessionKey: string): boolean {
  return sessionKey.includes(":workbench:");
}

export function capabilityBaseUrl(config?: PluginConfig): string {
  return (config?.baseUrl ?? process.env.NEXTERP_CAPABILITY_API_URL ?? "http://127.0.0.1:8790").replace(/\/$/, "");
}

export async function capabilityRequest(
  path: string,
  identity: TrustedToolIdentity,
  options: { method?: "GET" | "POST"; body?: unknown; config?: PluginConfig; signal?: AbortSignal } = {},
): Promise<Record<string, unknown>> {
  const token = process.env.NEXTERP_CAPABILITY_API_TOKEN;
  if (!token) {
    throw new Error("NEXTERP_CAPABILITY_API_TOKEN is not configured");
  }
  const timeout = options.config?.requestTimeoutMs ?? 30_000;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new Error("Nexterp Capability API timeout")), timeout);
  const abort = () => controller.abort(options.signal?.reason);
  options.signal?.addEventListener("abort", abort, { once: true });
  try {
    const response = await fetch(`${capabilityBaseUrl(options.config)}${path}`, {
      method: options.method ?? "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        "X-Nexterp-External-Subject": identity.externalSubject,
        "X-Nexterp-Agent-Id": identity.agentId,
        "X-Nexterp-Session-Key": identity.sessionKey,
      },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
    });
    const payload = (await response.json()) as Record<string, unknown>;
    if (!response.ok || payload.ok === false) {
      throw new Error(String(payload.message ?? payload.error_type ?? `Capability API ${response.status}`));
    }
    return payload;
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", abort);
  }
}

export function trustedIdentity(ctx: {
  requesterSenderId?: string;
  agentId?: string;
  sessionKey?: string;
}): TrustedToolIdentity {
  const developmentSubject = process.env.NEXTERP_OPENCLAW_DEV_SUBJECT;
  const externalSubject = ctx.requesterSenderId ?? developmentSubject;
  if (!externalSubject) {
    throw new Error("Trusted OpenClaw requester identity is unavailable");
  }
  if (!ctx.sessionKey) {
    throw new Error("Trusted OpenClaw sessionKey is unavailable");
  }
  return {
    externalSubject,
    agentId: ctx.agentId ?? "",
    sessionKey: ctx.sessionKey,
  };
}
