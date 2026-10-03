import { afterEach, describe, expect, it, vi } from "vitest";
import { changeOperator, createOperator, createOperatorSchema, listOperators, resetPasswordSchema } from "./operatorClient";

vi.mock("./authToken", () => ({ getAuthToken: () => "test-only-token" }));
afterEach(() => vi.unstubAllGlobals());
const signal = () => new AbortController().signal;
const operator = { sub: "operator-id", email: "operator@example.test", locale: "es", role: "operator", identity_version: 2, name: null, status: "active", updated_at: "2026-10-03T15:40:50Z" };
const input = { email: "Operator@example.test", password: "test-only-password", locale: "es" as const, first_name: "First", last_name: "Last" };

describe("allowlisted operator identity API", () => {
  it.each(["active", "inactive"])("accepts persisted %s lifecycle state", async (status) => {
    const persisted = { ...operator, status };
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify([persisted])));
    vi.stubGlobal("fetch", fetch);
    expect(await listOperators(signal())).toEqual([persisted]);
    expect(new URL(fetch.mock.calls[0][0], "https://bff.example.test").pathname).toBe("/admin/operators");
    expect(fetch.mock.calls[0][1]).toMatchObject({ method: "GET" });
    expect(fetch.mock.calls[0][1]).not.toHaveProperty("body");
  });
  it.each([{ ...operator, role: "admin" }, { ...operator, customer_id: "customer" }, { ...operator, identity_version: 0 }, { ...operator, status: undefined }, { ...operator, status: "unknown" }])("rejects malformed operator profiles", async (invalid) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify([invalid]))));
    await expect(listOperators(signal())).rejects.toMatchObject({ code: "SERVICE_UNAVAILABLE" });
  });
  it.each(["2026-10-03T15:40:50Z", "2026-10-03T10:40:50.575-05:00"])("preserves ISO update timestamp %s", async (updated_at) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify([{ ...operator, updated_at }]))));
    expect((await listOperators(signal()))[0].updated_at).toBe(updated_at);
  });
  it.each([undefined, null, "invalid", "2026-13-03T15:40:50Z"])("rejects invalid update timestamp %j", async (updated_at) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify([{ ...operator, updated_at }]))));
    await expect(listOperators(signal())).rejects.toMatchObject({ code: "SERVICE_UNAVAILABLE" });
  });
  it("sends only validated creation fields; the server assigns the role", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(null, { status: 201 }));
    vi.stubGlobal("fetch", fetch);
    await createOperator(input, signal());
    expect(new URL(fetch.mock.calls[0][0], "https://bff.example.test").pathname).toBe("/admin/operators");
    expect(fetch.mock.calls[0][1].method).toBe("POST");
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ ...input, email: input.email.toLowerCase() });
  });
  it.each(["activate", "deactivate"] as const)("POSTs %s without a body", async (action) => {
    const fetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetch);
    await changeOperator("operator-id", action, signal());
    expect(new URL(fetch.mock.calls[0][0], "https://bff.example.test").pathname).toBe(`/admin/operators/operator-id/${action}`);
    expect(fetch.mock.calls[0][1].method).toBe("POST");
    expect(fetch.mock.calls[0][1]).not.toHaveProperty("body");
    expect(fetch.mock.calls[0][1].headers).not.toHaveProperty("Content-Type");
  });
  it("sends only the transient password for reset", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetch);
    await changeOperator("operator-id", "reset-password", signal(), input.password);
    expect(new URL(fetch.mock.calls[0][0], "https://bff.example.test").pathname).toBe("/admin/operators/operator-id/reset-password");
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ password: input.password });
  });
  it("trims structured names and accepts exact length boundaries", () => {
    const boundary = { ...input, email: `${"a".repeat(60)}@${"b".repeat(55)}.com`, first_name: "f".repeat(50), last_name: "l".repeat(50) };
    expect(boundary.email).toHaveLength(120);
    expect(createOperatorSchema.safeParse(boundary).success).toBe(true);
    expect(createOperatorSchema.parse({ ...input, first_name: " First ", last_name: " Last " })).toMatchObject({ first_name: "First", last_name: "Last" });
  });
  it.each([
    { first_name: undefined }, { last_name: undefined }, { first_name: " " },
    { last_name: " " }, { first_name: "x".repeat(51) }, { last_name: "x".repeat(51) },
    { email: `${"a".repeat(60)}@${"b".repeat(56)}.com` },
  ])("rejects invalid structured fields before transport: %j", async (fields) => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    await expect(createOperator({ ...input, ...fields } as typeof input, signal())).rejects.toMatchObject({ code: "INVALID_REQUEST" });
    expect(fetch).not.toHaveBeenCalled();
  });
  it("preserves structured operator response fields", async () => {
    const persisted = { ...operator, first_name: "First", last_name: "Last", name: "First Last" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify([persisted]))));
    expect(await listOperators(signal())).toEqual([persisted]);
  });
  it.each(["role", "customer_id", "is_active", "name"])("rejects unexpected creation field %s", (field) => {
    expect(createOperatorSchema.safeParse({ ...input, [field]: "injected" }).success).toBe(false);
  });
  it.each(["short", "x".repeat(257)])("rejects passwords outside policy", (password) => {
    expect(createOperatorSchema.safeParse({ ...input, password }).success).toBe(false);
    expect(resetPasswordSchema.safeParse({ password }).success).toBe(false);
  });
  it("rejects extra reset fields and invalid locale", () => {
    expect(resetPasswordSchema.safeParse({ password: input.password, role: "admin" }).success).toBe(false);
    expect(createOperatorSchema.safeParse({ ...input, locale: "fr" }).success).toBe(false);
  });
  it.each(["", " ", ".", ".."]) ("rejects unsafe target %j before transport", async (id) => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    await expect(changeOperator(id, "activate", signal())).rejects.toMatchObject({ code: "INVALID_REQUEST" });
    expect(fetch).not.toHaveBeenCalled();
  });
  it("does not display server detail or accept an unauthorized response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "private server detail" }), { status: 403 })));
    await expect(listOperators(signal())).rejects.toMatchObject({ code: "ACCESS_DENIED" });
  });
  it("propagates cancellation even when fetch resolves", async () => {
    const controller = new AbortController();
    controller.abort();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify([operator]))));
    await expect(listOperators(controller.signal)).rejects.toMatchObject({ name: "AbortError" });
  });
});
