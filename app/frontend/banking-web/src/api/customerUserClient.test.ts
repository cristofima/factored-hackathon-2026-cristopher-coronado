import { afterEach, describe, expect, it, vi } from "vitest";
import { changeCustomerUser, listCustomerUsers, type CustomerUserAction } from "./customerUserClient";

const auth = vi.hoisted(() => ({ token: "test-only-token" as string | null }));
vi.mock("./authToken", () => ({ getAuthToken: () => auth.token }));
afterEach(() => { vi.unstubAllGlobals(); auth.token = "test-only-token"; });
const signal = () => new AbortController().signal;
const customer = { sub: "customer-id", customer_id: "banking-customer-id", email: "customer@example.test", locale: "es", role: "customer", identity_version: 2, name: null, status: "active", updated_at: "2026-10-03T15:40:50Z" };

describe("BFF-only customer user lifecycle API", () => {
  it.each(["active", "inactive"])("accepts persisted %s customer membership", async (status) => {
    const persisted = { ...customer, status };
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify([persisted])));
    vi.stubGlobal("fetch", fetch);
    expect(await listCustomerUsers(signal())).toEqual([persisted]);
    expect(new URL(fetch.mock.calls[0][0]).pathname).toBe("/admin/customers");
    expect(fetch.mock.calls[0][0]).not.toContain("8090");
    expect(fetch.mock.calls[0][1]).toMatchObject({ method: "GET", headers: { Authorization: "Bearer test-only-token" } });
    expect(fetch.mock.calls[0][1]).not.toHaveProperty("body");
  });
  it.each([{ role: "admin" }, { role: "operator" }, { customer_id: undefined }, { customer_id: " " }, { identity_version: true }, { identity_version: 0 }, { status: "unknown" }, { updated_at: "invalid" }, { sub: "../internal" }])("rejects malformed profiles %j", async (fields) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify([{ ...customer, ...fields }]))));
    await expect(listCustomerUsers(signal())).rejects.toMatchObject({ code: "SERVICE_UNAVAILABLE" });
  });
  it("maps invalid JSON to a safe unavailable error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("not JSON")));
    await expect(listCustomerUsers(signal())).rejects.toMatchObject({ code: "SERVICE_UNAVAILABLE" });
  });
  it.each(["activate", "deactivate"] as const)("POSTs only allowlisted %s", async (action) => {
    const fetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetch);
    await changeCustomerUser("customer-id", action, signal());
    expect(new URL(fetch.mock.calls[0][0]).pathname).toBe(`/admin/customers/customer-id/${action}`);
    expect(fetch.mock.calls[0][1]).toMatchObject({ method: "POST" });
    expect(fetch.mock.calls[0][1]).not.toHaveProperty("body");
  });
  it.each(["", " ", ".", "..", "bad/id", "x".repeat(129)])("rejects unsafe target %j", async (id) => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    await expect(changeCustomerUser(id, "activate", signal())).rejects.toMatchObject({ code: "INVALID_REQUEST" });
    expect(fetch).not.toHaveBeenCalled();
  });
  it("rejects unsupported actions before transport", async () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    await expect(changeCustomerUser("customer-id", "reset-password" as CustomerUserAction, signal())).rejects.toMatchObject({ code: "INVALID_REQUEST" });
    expect(fetch).not.toHaveBeenCalled();
  });
  it("rejects missing authentication before transport", async () => {
    auth.token = null;
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    await expect(listCustomerUsers(signal())).rejects.toMatchObject({ code: "AUTH_REQUIRED" });
    await expect(changeCustomerUser("customer-id", "activate", signal())).rejects.toMatchObject({ code: "AUTH_REQUIRED" });
    expect(fetch).not.toHaveBeenCalled();
  });
  it.each([[401, "AUTH_REQUIRED"], [403, "ACCESS_DENIED"], [404, "SERVICE_UNAVAILABLE"], [503, "SERVICE_UNAVAILABLE"]])("maps HTTP %s without exposing raw details", async (status, code) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "private upstream message" }), { status: status as number })));
    await expect(listCustomerUsers(signal())).rejects.toMatchObject({ code });
  });
  it("propagates cancellation after transport resolves", async () => {
    const controller = new AbortController(); controller.abort();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify([customer]))));
    await expect(listCustomerUsers(controller.signal)).rejects.toMatchObject({ name: "AbortError" });
  });
});
