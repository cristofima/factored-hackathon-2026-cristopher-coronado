import { beforeEach, describe, expect, it, vi } from "vitest";
import { getSupportCase, getCaseConversation, listSupportCases, previewSupportCase, openSupportCase, recoverSupportCase } from "./disputeClient";
import { getAuthToken } from "./authToken";
import { isTerminalCase, type ConversationMessage } from "./supportCaseContracts";
vi.mock("@/api/authToken", () => ({ getAuthToken: vi.fn(() => "test-only") }));
const record = {
  caseId: "case", transactionId: "transaction", productNumber: null, reason: "Customer reason",
  status: "IN_REVIEW", triageOutcome: null, resolutionOutcome: null, resolutionNotes: null,
  recommendationType: null, recommendationRationale: null, recommendationOptedOut: false,
  openedAt: "2026-10-04T10:00:00Z", updatedAt: "2026-10-04T10:00:00Z", resolvedAt: null,
};
beforeEach(() => {
  vi.unstubAllGlobals();
  vi.mocked(getAuthToken).mockReset().mockReturnValue("test-only");
});
const preview = { previewToken: "signed", transactionId: "transaction", reason: "Customer reason", expiresAt: "2026-10-04T10:10:00Z", transaction: { id: "transaction", country: "CO", city: null } };
describe("signed dispute preview contracts", () => {
  it("previews owned context and strips unsupported fraud fields", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...preview, transaction: { ...preview.transaction, fraud_score: 0.2 } })));
    vi.stubGlobal("fetch", fetch);
    expect(await previewSupportCase("transaction", "Customer reason")).toEqual(preview);
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ transactionId: "transaction", reason: "Customer reason" });
  });
  it.each([{ transactionId: "foreign" }, { reason: "changed" }, { transaction: { id: "foreign" } }, { expiresAt: "invalid" }])("rejects unbound or malformed preview %j", async invalid => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...preview, ...invalid }))));
    await expect(previewSupportCase("transaction", "Customer reason")).rejects.toMatchObject({ code: "SERVICE_UNAVAILABLE" });
  });
  it("posts only the token for acceptance and bounded recovery", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(record)))
      .mockResolvedValueOnce(new Response(JSON.stringify(record)))
      .mockResolvedValueOnce(new Response("null"));
    vi.stubGlobal("fetch", fetch);
    expect(await openSupportCase("signed")).toEqual(record);
    expect(await recoverSupportCase("signed")).toEqual(record);
    expect(await recoverSupportCase("signed")).toBeNull();
    for (const [, options] of fetch.mock.calls) expect(JSON.parse(options.body)).toEqual({ previewToken: "signed" });
    expect(fetch.mock.calls[1][0]).toMatch(/support-cases\/recovery$/);
  });
});
describe("customer case contracts", () => {
  it.each(["OPEN", "WAITING_USER_APPROVAL", "IN_REVIEW", "PENDING_EFFECTS", "RESOLVED_VALID", "RESOLVED_INVALID", "RESOLVED"])("accepts %s in detail and list", async status => {
    const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ ...record, status })))
      .mockResolvedValueOnce(new Response(JSON.stringify([{ ...record, status }])));
    vi.stubGlobal("fetch", fetch);
    expect((await getSupportCase("case")).status).toBe(status);
    expect((await listSupportCases())[0].status).toBe(status);
    expect(isTerminalCase(status)).toBe(status.startsWith("RESOLVED"));
  });
  it("fails closed for malformed/unknown statuses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...record, status: "CREDIT_COMPLETE" }))));
    await expect(getSupportCase("case")).rejects.toMatchObject({ code: "SERVICE_UNAVAILABLE" });
  });
  it("decodes shared recorded financial effects and nullable protection audit", async () => {
    const enriched = { ...record, caseVersion: 3, verdict: "valid", rationale: "Reviewed", effectCode: null, effects: { movementId: "movement", destinationProductId: "savings", amount: "10.00", currency: "USD", balanceDelta: "10.00", executedAt: "2026-10-04T12:00:00" }, cardProtection: { blocked: true, priorStatus: null, rationale: "Protect card", caseId: "prior-case", updatedAt: "2026-10-04T12:00:00", scope: "LOCAL_PRODUCT_ONLY" } };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(enriched))));
    expect(await getSupportCase("case")).toMatchObject(enriched);
  });
  it.each([{ amount: "invalid" }, { executedAt: "invalid" }, { movementId: "" }])("rejects malformed financial posting %j", invalid => {
    const effects = { movementId: "movement", destinationProductId: "savings", amount: "10.00", currency: "USD", balanceDelta: "10.00", executedAt: "2026-10-04T12:00:00Z", ...invalid };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...record, effects }))));
    return expect(getSupportCase("case")).rejects.toMatchObject({ code: "SERVICE_UNAVAILABLE" });
  });
  it("honors abort after response decoding", async () => {
    const controller = new AbortController();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => {
      controller.abort(); return record;
    } }));
    await expect(getSupportCase("case", controller.signal)).rejects.toMatchObject({ name: "AbortError" });
  });
});

const conversation = { source: "CUSTOMER_PROVIDED", messages: [{ role: "user" as const, text: "Customer text\n<literal>" }, { role: "assistant" as const, text: "Assistant text" }] };
const invalidHistories: Array<{ label: string; messages: unknown }> = [
  { label: "null", messages: null },
  { label: "non-array", messages: {} },
  { label: "missing message fields", messages: [{}] },
  { label: "system role", messages: [{ role: "system", text: "text" }] },
  { label: "empty text", messages: [{ role: "user", text: "" }] },
  { label: "non-string text", messages: [{ role: "user", text: 1 }] },
  { label: "message count", messages: Array.from({ length: 101 }, () => ({ role: "user", text: "x" })) },
  { label: "message size", messages: [{ role: "user", text: "x".repeat(100001) }] },
  { label: "aggregate size", messages: [{ role: "user", text: "x".repeat(50000) }, { role: "assistant", text: "y".repeat(50001) }] },
];

describe("customer conversation acceptance", () => {
  it.each([[], conversation.messages, [{ role: "user" as const, text: "x".repeat(100000) }], Array.from({ length: 100 }, () => ({ role: "assistant" as const, text: "x".repeat(1000) }))].map(messages => ({ messages })))("transports supplied history including empty and exact bounds %#", async ({ messages }) => {
    const controller = new AbortController();
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(record)));
    vi.stubGlobal("fetch", fetch);
    expect(await openSupportCase("signed", controller.signal, messages)).toEqual(record);
    expect(fetch.mock.calls[0][0]).toMatch(/\/support-cases$/);
    expect(fetch.mock.calls[0][1]).toMatchObject({ method: "POST", signal: controller.signal, headers: { "Content-Type": "application/json", Authorization: `Bearer test-only` } });
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ previewToken: "signed", conversationHistory: messages });
  });
  it.each(invalidHistories)("rejects $label before fetch", async ({ messages }) => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    await expect(openSupportCase("signed", undefined, messages as ConversationMessage[])).rejects.toMatchObject({ code: "INVALID_REQUEST" });
    expect(fetch).not.toHaveBeenCalled();
  });
  it("does not accept history without authentication or after cancellation", async () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    vi.mocked(getAuthToken).mockReturnValue(null);
    await expect(openSupportCase("signed", undefined, conversation.messages)).rejects.toMatchObject({ code: "AUTH_REQUIRED" });
    const controller = new AbortController(); controller.abort();
    await expect(openSupportCase("signed", controller.signal, conversation.messages)).rejects.toMatchObject({ name: "AbortError" });
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe("customer conversation getter", () => {
  it.each([conversation.messages, []].map(messages => ({ messages })))("decodes history and uses an encoded authenticated read %#", async ({ messages }) => {
    const controller = new AbortController();
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...conversation, messages })));
    vi.stubGlobal("fetch", fetch);
    expect(await getCaseConversation("case /?#", controller.signal)).toEqual({ ...conversation, messages });
    expect(fetch.mock.calls[0][0]).toMatch(/\/support-cases\/case%20%2F%3F%23\/conversation$/);
    expect(fetch.mock.calls[0][1]).toMatchObject({ signal: controller.signal, headers: { Authorization: `Bearer test-only` } });
    expect(fetch.mock.calls[0][1]).not.toHaveProperty("body");
  });
  it("strips unsupported response fields without changing text", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...conversation, privateField: "ignored", messages: conversation.messages.map(message => ({ ...message, privateField: "ignored" })) }))));
    expect(await getCaseConversation("case")).toEqual(conversation);
  });
  it.each(invalidHistories)("rejects malformed response $label", async ({ messages }) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...conversation, messages }))));
    await expect(getCaseConversation("case")).rejects.toMatchObject({ code: "SERVICE_UNAVAILABLE" });
  });
  it.each([null, {}, { ...conversation, source: "MODEL_VERIFIED" }])("rejects malformed envelope %#", async payload => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(payload))));
    await expect(getCaseConversation("case")).rejects.toMatchObject({ code: "SERVICE_UNAVAILABLE" });
  });
  it("rejects invalid JSON with a controlled error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("private malformed response")));
    await expect(getCaseConversation("case")).rejects.toMatchObject({ code: "SERVICE_UNAVAILABLE" });
  });
  it.each([[401, "AUTH_REQUIRED"], [403, "ACCESS_DENIED"], [404, "CASE_NOT_FOUND"]] as const)("preserves controlled %s errors", async (status, code) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { code } }), { status })));
    await expect(getCaseConversation("case")).rejects.toMatchObject({ code });
  });
  it("fails before fetch when unauthenticated or already aborted", async () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    vi.mocked(getAuthToken).mockReturnValue(null);
    await expect(getCaseConversation("case")).rejects.toMatchObject({ code: "AUTH_REQUIRED" });
    const controller = new AbortController(); controller.abort();
    await expect(getCaseConversation("case", controller.signal)).rejects.toMatchObject({ name: "AbortError" });
    expect(fetch).not.toHaveBeenCalled();
  });
  it("does not decode a response received after cancellation", async () => {
    const controller = new AbortController();
    const json = vi.fn().mockResolvedValue(conversation);
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => {
      controller.abort();
      return { ok: true, json };
    }));
    await expect(getCaseConversation("case", controller.signal)).rejects.toMatchObject({ name: "AbortError" });
    expect(json).not.toHaveBeenCalled();
  });
  it.each(["success", "malformed JSON", "error", "malformed error JSON"])("preserves cancellation during %s decoding", async kind => {
    const controller = new AbortController();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: !kind.includes("error"), status: 401, json: async () => {
      controller.abort();
      if (kind.includes("JSON")) throw new SyntaxError("private response");
      return kind === "success" ? conversation : { detail: { code: "AUTH_REQUIRED" } };
    } }));
    await expect(getCaseConversation("case", controller.signal)).rejects.toMatchObject({ name: "AbortError" });
  });
});
