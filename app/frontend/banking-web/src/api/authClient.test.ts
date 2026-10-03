import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { login, mapUser, restoreUser } from "./authClient";
import { AUTH_TOKEN_KEY } from "./authToken";

const profile = { sub: "identity", email: "user@example.test", locale: "es", identity_version: 1 };
let storage: Map<string, string>;
beforeEach(() => {
  storage = new Map();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
  });
});
afterEach(() => vi.unstubAllGlobals());

describe("identity profile trust boundary", () => {
  it.each(["operator", "admin"])("maps %s without a customer", (role) => {
    expect(mapUser({ ...profile, role })).toEqual({ id: "identity", email: profile.email, locale: "es", name: null, identityVersion: 1, role });
    expect(mapUser({ ...profile, role })).not.toHaveProperty("customerId");
  });
  it("retains customer mapping and optional name", () => {
    expect(mapUser({ ...profile, role: "customer", customer_id: "customer", name: "Name" })).toMatchObject({ customerId: "customer", name: "Name", role: "customer" });
  });
  it.each([
    { role: "unknown" }, { role: "customer" }, { role: "customer", customer_id: " " },
    { role: "admin", customer_id: "customer" }, { role: "operator", customer_id: null },
    { role: "admin", identity_version: undefined }, { role: "admin", identity_version: 0 },
    { role: "admin", identity_version: 1.5 }, { role: "admin", identity_version: "1" },
  ])("rejects invalid profile %j", (overrides) => {
    expect(() => mapUser({ ...profile, ...overrides })).toThrow();
  });
  it("never persists a login token from an invalid profile", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ access_token: "test-only-token", user: profile }))));
    await expect(login("user@example.test", "test-password")).rejects.toMatchObject({ code: "AUTH_REQUIRED" });
    expect(storage.size).toBe(0);
  });
  it("persists only the JWT, not the password or profile", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ access_token: "test-only-token", user: { ...profile, role: "operator" } }))));
    await login("user@example.test", "test-password");
    expect([...storage.entries()]).toEqual([[AUTH_TOKEN_KEY, "test-only-token"]]);
  });
  it("does not persist a canceled login after parsing its response", async () => {
    const controller = new AbortController();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => {
      controller.abort();
      return { access_token: "test-only-token", user: { ...profile, role: "admin" } };
    } }));
    await expect(login(profile.email, "test-password", controller.signal)).rejects.toMatchObject({ name: "AbortError" });
    expect(storage.size).toBe(0);
  });
  it("does not remove the new session when an old restore fails", async () => {
    storage.set(AUTH_TOKEN_KEY, "old-test-token");
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => {
      storage.set(AUTH_TOKEN_KEY, "new-test-token");
      return new Response(null, { status: 401 });
    }));
    expect(await restoreUser()).toBeNull();
    expect(storage.get(AUTH_TOKEN_KEY)).toBe("new-test-token");
  });
  it("rejects an old successful restore without removing a newer session", async () => {
    storage.set(AUTH_TOKEN_KEY, "old-test-token");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => {
      storage.set(AUTH_TOKEN_KEY, "new-test-token");
      return { ...profile, role: "customer", customer_id: "old-customer" };
    } }));
    await expect(restoreUser()).rejects.toMatchObject({ name: "AbortError" });
    expect(storage.get(AUTH_TOKEN_KEY)).toBe("new-test-token");
  });
  it("rejects canceled restores after JSON parsing without clearing the token", async () => {
    storage.set(AUTH_TOKEN_KEY, "test-only-token");
    const controller = new AbortController();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => {
      controller.abort();
      return { ...profile, role: "admin" };
    } }));
    await expect(restoreUser(controller.signal)).rejects.toMatchObject({ name: "AbortError" });
    expect(storage.get(AUTH_TOKEN_KEY)).toBe("test-only-token");
  });
});
