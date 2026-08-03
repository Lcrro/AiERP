import { afterEach, describe, expect, it, vi } from "vitest";

import { capabilityRequest, isPreviewOnlySession, isWorkbenchSession, trustedIdentity } from "./client.js";

afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.NEXTERP_CAPABILITY_API_TOKEN;
  delete process.env.NEXTERP_OPENCLAW_DEV_SUBJECT;
});

describe("trustedIdentity", () => {
  it("uses runtime-provided requester and never accepts model parameters", () => {
    expect(trustedIdentity({ requesterSenderId: "sender-1", agentId: "nexterp", sessionKey: "session-1" })).toEqual({
      externalSubject: "sender-1",
      agentId: "nexterp",
      sessionKey: "session-1",
    });
  });

  it("fails closed without trusted identity", () => {
    expect(() => trustedIdentity({ sessionKey: "session-1" })).toThrow("requester identity");
  });
});

describe("preview sessions", () => {
  it("recognizes comparison sessions as write-blocked", () => {
    expect(isPreviewOnlySession("agent:main:compare-preview:abc")).toBe(true);
    expect(isPreviewOnlySession("agent:main:normal-session")).toBe(false);
  });
});

describe("workbench sessions", () => {
  it("recognizes sessions whose writes must be confirmed by the workbench", () => {
    expect(isWorkbenchSession("agent:main:workbench:abc")).toBe(true);
    expect(isWorkbenchSession("agent:main:normal-session")).toBe(false);
  });
});

describe("capabilityRequest", () => {
  it("injects the service token and trusted identity headers", async () => {
    process.env.NEXTERP_CAPABILITY_API_TOKEN = "test-token";
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      const headers = init.headers as Record<string, string>;
      expect(headers.Authorization).toBe("Bearer test-token");
      expect(headers["X-Nexterp-External-Subject"]).toBe("sender-1");
      expect(headers["X-Nexterp-Session-Key"]).toBe("session-1");
      return new Response(JSON.stringify({ ok: true, status: "found" }), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(capabilityRequest("/api/capabilities/search", {
      externalSubject: "sender-1", agentId: "nexterp", sessionKey: "session-1",
    }, { body: { query: "材料申请" } })).resolves.toMatchObject({ status: "found" });
  });
});
