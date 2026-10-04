import { afterEach, describe, expect, it, vi } from "vitest";
import { claimOperatorCase, getOperatorCase, listOperatorCases } from "./operatorDisputeClient";

vi.mock("./authToken", () => ({ getAuthToken: vi.fn(() => "test-only-token") }));
afterEach(() => vi.unstubAllGlobals());
const supportCase = {
  caseId: "case-id", status: "IN_REVIEW", triageOutcome: null,
  openedAt: "2026-10-04T12:00:00Z", updatedAt: "2026-10-04T12:00:00Z", claimVersion: 0,
};
const queue = { items: [supportCase], total: 1, offset: 0, limit: 50 };
const claimed = { ...supportCase, claimVersion: 1, assignedOperatorSub: "operator-id", claimedAt: supportCase.openedAt,
  reason: "Customer reason", transactionId: "transaction-id", productId: "product-id", events: [] };

describe("operator dispute transport", () => {
  it("reads the queue directly with the application bearer", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(queue)));
    vi.stubGlobal("fetch", fetch);
    expect(await listOperatorCases()).toEqual(queue);
    expect(fetch.mock.calls[0][0]).toContain("/operator/support-cases");
    expect(fetch.mock.calls[0][1]).toMatchObject({ method: "GET", headers: { Authorization: "Bearer test-only-token" } });
  });
  it.each(["available", "assigned"] as const)("transports the %s view with pagination", async (view) => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(queue)));
    vi.stubGlobal("fetch", fetch);
    await listOperatorCases(undefined, 0, 50, view);
    expect(fetch.mock.calls[0][0]).toContain(`?offset=0&limit=50&view=${view}`);
  });
  it("rejects an unsupported view before transport", async () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    await expect(listOperatorCases(undefined, 0, 50, "all" as "available")).rejects.toMatchObject({ code: "INVALID_REQUEST" });
    expect(fetch).not.toHaveBeenCalled();
  });
  it("validates flat owned detail and sends a bodyless claim", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(claimed)))
      .mockResolvedValueOnce(new Response(JSON.stringify(claimed)));
    vi.stubGlobal("fetch", fetch);
    expect(await getOperatorCase("case-id")).toEqual(claimed);
    expect(await claimOperatorCase("case-id")).toEqual(claimed);
    expect(fetch.mock.calls[1][0]).toContain("/case-id/claim");
    expect(fetch.mock.calls[1][1]).toMatchObject({ method: "POST" });
    expect(fetch.mock.calls[1][1]).not.toHaveProperty("body");
  });
  it.each(["", " ", ".", ".."]) ("rejects unsafe identifier %j", async (id) => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    await expect(getOperatorCase(id)).rejects.toMatchObject({ code: "INVALID_REQUEST" });
    await expect(claimOperatorCase(id)).rejects.toMatchObject({ code: "INVALID_REQUEST" });
    expect(fetch).not.toHaveBeenCalled();
  });
  it.each([-1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1])("rejects invalid offset %j", async (offset) => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    await expect(listOperatorCases(undefined, offset)).rejects.toMatchObject({ code: "INVALID_REQUEST" });
    expect(fetch).not.toHaveBeenCalled();
  });
  it.each([{ ...supportCase, claimVersion: -1 }, { ...supportCase, status: "UNKNOWN" }, { ...supportCase, openedAt: "invalid" }, { ...supportCase, triageOutcome: undefined }])("rejects malformed records", async (invalid) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...queue, items: [invalid] }))));
    await expect(listOperatorCases()).rejects.toMatchObject({ code: "SERVICE_UNAVAILABLE" });
  });
  it.each([0, 101, 1.5, NaN, Infinity])("rejects invalid limit %j", async (limit) => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    await expect(listOperatorCases(undefined, 0, limit)).rejects.toMatchObject({ code: "INVALID_REQUEST" });
    expect(fetch).not.toHaveBeenCalled();
  });
  it.each([1, 100])("transports pagination with limit %j", async (limit) => {
    const page = { ...queue, offset: 50, limit, total: 101 };
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(page)));
    vi.stubGlobal("fetch", fetch);
    expect(await listOperatorCases(undefined, 50, limit)).toEqual(page);
    expect(fetch.mock.calls[0][0]).toContain(`?offset=50&limit=${limit}`);
  });
  it.each(["2026-10-04T12:00:00", "2026-10-04T12:00:00+00:00"])("accepts backend timestamp %s and audited events", async (createdAt) => {
    const detail = { ...claimed, claimedAt: createdAt, events: [{
      eventId: "event-id", eventType: "OPERATOR_CLAIMED", actor: "operator", message: null,
      createdAt, operatorSub: "operator-id", operatorIdentityVersion: 3, claimVersion: 1,
    }] };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(detail))));
    expect(await getOperatorCase("case-id")).toEqual(detail);
  });
  it("preserves the owner-only not-found response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { code: "CASE_NOT_FOUND" } }), { status: 404 })));
    await expect(getOperatorCase("foreign-case")).rejects.toMatchObject({ code: "CASE_NOT_FOUND" });
  });
  it("rejects malformed JSON without exposing its contents", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("private malformed response")));
    await expect(listOperatorCases()).rejects.toMatchObject({ code: "SERVICE_UNAVAILABLE" });
  });
  it("preserves a controlled claim conflict", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { code: "OPERATOR_CLAIM_CONFLICT" } }), { status: 409 })));
    await expect(claimOperatorCase("case-id")).rejects.toMatchObject({ code: "OPERATOR_CLAIM_CONFLICT" });
  });
  it("does not transport an already aborted request", async () => {
    const controller = new AbortController(); controller.abort();
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    await expect(listOperatorCases(controller.signal)).rejects.toMatchObject({ name: "AbortError" });
    expect(fetch).not.toHaveBeenCalled();
  });
  it("rejects cancellation during JSON decoding", async () => {
    const controller = new AbortController();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => { controller.abort(); return [supportCase]; } }));
    await expect(listOperatorCases(controller.signal)).rejects.toMatchObject({ name: "AbortError" });
  });
  it("preserves cancellation when JSON decoding fails", async () => {
    const controller = new AbortController();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => { controller.abort(); throw new SyntaxError(); } }));
    await expect(listOperatorCases(controller.signal)).rejects.toMatchObject({ name: "AbortError" });
  });
  it("preserves cancellation while decoding a controlled error", async () => {
    const controller = new AbortController();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 409, json: async () => { controller.abort(); return { detail: { code: "OPERATOR_CLAIM_CONFLICT" } }; } }));
    await expect(claimOperatorCase("case-id", controller.signal)).rejects.toMatchObject({ name: "AbortError" });
  });
  it("rejects a malformed detail envelope", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ supportCase, timeline: [{}] }))));
    await expect(getOperatorCase("case-id")).rejects.toMatchObject({ code: "SERVICE_UNAVAILABLE" });
  });
});
