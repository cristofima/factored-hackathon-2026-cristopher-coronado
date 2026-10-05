import { beforeEach, describe, expect, it, vi } from "vitest";
import { getSupportCase, listSupportCases, previewSupportCase, openSupportCase, recoverSupportCase } from "./disputeClient";
import { isTerminalCase } from "./supportCaseContracts";
vi.mock("@/api/authToken", () => ({ getAuthToken: () => "test-only" }));
const record = {
  caseId: "case", transactionId: "transaction", productNumber: null, reason: "Customer reason",
  status: "IN_REVIEW", triageOutcome: null, resolutionOutcome: null, resolutionNotes: null,
  recommendationType: null, recommendationRationale: null, recommendationOptedOut: false,
  openedAt: "2026-10-04T10:00:00Z", updatedAt: "2026-10-04T10:00:00Z", resolvedAt: null,
};
beforeEach(() => vi.unstubAllGlobals());
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
