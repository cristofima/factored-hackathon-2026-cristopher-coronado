import { beforeEach, describe, expect, it, vi } from "vitest";
import { useProductCatalog } from "./useProductCatalog";
import { ApiError } from "@/api/errors";

const h = vi.hoisted(() => ({
  states: [] as unknown[], cursor: 0, deps: [] as unknown[][],
  effects: [] as Array<() => void>, cleanups: [] as Array<(() => void) | undefined>,
  user: { id: "customer-a", identityVersion: 1 }, sessionKey: 1,
  accounts: vi.fn(), cards: vi.fn(), logout: vi.fn(),
}));
vi.mock("react", () => ({
  useState: (initial: unknown) => {
    const index = h.cursor++;
    if (!(index in h.states)) h.states[index] = initial;
    return [h.states[index], (value: unknown) => {
      h.states[index] = typeof value === "function" ? value(h.states[index]) : value;
    }];
  },
  useEffect: (effect: () => void | (() => void), deps: unknown[]) => {
    const index = h.cursor++;
    if (!h.deps[index] || deps.some((dep, i) => !Object.is(dep, h.deps[index][i]))) {
      h.deps[index] = deps;
      h.effects.push(() => { h.cleanups[index]?.(); h.cleanups[index] = effect() || undefined; });
    }
  },
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: h.user, sessionKey: h.sessionKey, logout: h.logout }) }));
vi.mock("@/api/authClient", () => ({ getAccounts: h.accounts, getCards: h.cards }));
function RenderCatalog(key?: string) { h.cursor = 0; return useProductCatalog(key); }
function effects() { h.effects.splice(0).forEach(effect => effect()); }
async function settle() { for (let i = 0; i < 6; i++) await Promise.resolve(); }
beforeEach(() => {
  h.cleanups.forEach(cleanup => cleanup?.()); vi.resetAllMocks();
  h.states = []; h.deps = []; h.effects = []; h.cleanups = [];
  h.user = { id: "customer-a", identityVersion: 1 }; h.sessionKey = 1;
  h.accounts.mockResolvedValue([{ product_id: "destination", balance: "101.00" }]); h.cards.mockResolvedValue([]);
});
describe("persisted balance refresh", () => {
  it("reloads real records on posting change without displaying the previous balance", async () => {
    RenderCatalog(); effects(); await settle(); expect(RenderCatalog().accounts[0].balance).toBe("101.00");
    h.accounts.mockResolvedValue([{ product_id: "destination", balance: "126.00" }]);
    expect(RenderCatalog("movement-1").accounts).toEqual([]); effects(); await settle();
    expect(RenderCatalog("movement-1").accounts[0].balance).toBe("126.00");
    expect(h.accounts).toHaveBeenCalledTimes(2); expect(h.cards).toHaveBeenCalledTimes(2);
  });
  it("aborts old identity requests and rejects late data on version/session changes", async () => {
    let complete: (value: unknown[]) => void;
    h.accounts.mockImplementationOnce(() => new Promise(resolve => { complete = resolve; }));
    RenderCatalog(); effects(); const signal = h.accounts.mock.calls[0][0] as AbortSignal;
    h.user = { id: "customer-a", identityVersion: 2 }; h.sessionKey = 2;
    expect(RenderCatalog().accounts).toEqual([]); effects(); expect(signal.aborted).toBe(true);
    complete!([{ product_id: "old", balance: "999.00" }]); await settle();
    expect(RenderCatalog().accounts[0].product_id).toBe("destination");
  });
  it("logs out on a current authentication failure", async () => {
    h.accounts.mockRejectedValue(new ApiError("AUTH_REQUIRED"));
    RenderCatalog(); effects(); await settle(); expect(h.logout).toHaveBeenCalledOnce();
  });
  it("does not log out from an aborted stale authentication failure", async () => {
    let reject: (cause: unknown) => void;
    h.accounts.mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail; }));
    RenderCatalog(); effects(); h.sessionKey = 2; RenderCatalog(); effects();
    reject!(new ApiError("AUTH_REQUIRED")); await settle(); expect(h.logout).not.toHaveBeenCalled();
  });
  it("keeps failed refresh unavailable until explicit retry succeeds", async () => {
    h.accounts.mockRejectedValueOnce(new ApiError("SERVICE_UNAVAILABLE"));
    RenderCatalog(); effects(); await settle(); const failed = RenderCatalog();
    expect(failed.accounts).toEqual([]); expect(failed.error).not.toBeNull();
    failed.retry(); RenderCatalog(); effects(); await settle();
    expect(RenderCatalog().error).toBeNull(); expect(RenderCatalog().accounts[0].balance).toBe("101.00");
  });
});
