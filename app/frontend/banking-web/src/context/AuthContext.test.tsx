import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthenticatedUser } from "@/api/authClient";
import { AUTH_TOKEN_KEY } from "@/api/authToken";
import { AuthProvider } from "./AuthContext";

const harness = vi.hoisted(() => ({
  effects: [] as Array<() => void | (() => void)>,
  setters: [] as Array<ReturnType<typeof vi.fn>>,
  clear: vi.fn(), cancel: vi.fn(), dismiss: vi.fn(), resetToasts: vi.fn(),
  login: vi.fn(), restore: vi.fn(), remove: vi.fn(),
  addEventListener: vi.fn(), removeEventListener: vi.fn(),
}));
// Exercise the provider's asynchronous session orchestration without a browser DOM.
vi.mock("react", async (original) => ({
  ...await original<typeof import("react")>(),
  useCallback: (callback: unknown) => callback,
  useMemo: (factory: () => unknown) => factory(),
  useRef: (current: unknown) => ({ current }),
  useEffect: (effect: () => void | (() => void)) => harness.effects.push(effect),
  useState: (value: unknown) => {
    const setter = vi.fn();
    harness.setters.push(setter);
    return [value, setter];
  },
}));
vi.mock("@tanstack/react-query", () => ({ useQueryClient: () => ({ clear: harness.clear, cancelQueries: harness.cancel }) }));
vi.mock("sonner", () => ({ toast: { dismiss: harness.dismiss } }));
vi.mock("@/hooks/use-toast", () => ({ resetToasts: harness.resetToasts }));
vi.mock("@/api/authClient", () => ({ login: harness.login, restoreUser: harness.restore }));

const profile: AuthenticatedUser = { id: "admin", email: "admin@example.test", locale: "es", name: null, role: "admin", identityVersion: 2 };
const flush = async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); };
const provider = () => AuthProvider({ children: null }).props.value;

beforeEach(() => {
  vi.clearAllMocks();
  harness.effects.length = 0;
  harness.setters.length = 0;
  harness.cancel.mockResolvedValue(undefined);
  harness.restore.mockResolvedValue(null);
  vi.stubGlobal("localStorage", { removeItem: harness.remove });
  vi.stubGlobal("window", { addEventListener: harness.addEventListener, removeEventListener: harness.removeEventListener });
});

 describe("session isolation orchestration", () => {
  it("clears queries, mutations and toasts and advances the shell epoch on logout", () => {
    const auth = provider();
    auth.logout();
    expect(harness.cancel).toHaveBeenCalledOnce();
    expect(harness.clear).toHaveBeenCalledOnce();
    expect(harness.resetToasts).toHaveBeenCalledOnce();
    expect(harness.dismiss).toHaveBeenCalledOnce();
    expect(harness.setters[0]).toHaveBeenCalledWith(null);
    expect(harness.setters[1]).toHaveBeenCalledWith(false);
    const increment = harness.setters[2].mock.calls[0][0];
    expect(increment(3)).toBe(4);
    expect(harness.remove).toHaveBeenCalledWith(AUTH_TOKEN_KEY);
  });
  it("aborts an old login on logout and never publishes its late profile", async () => {
    let complete: (value: AuthenticatedUser) => void = () => undefined;
    harness.login.mockImplementation(() => new Promise<AuthenticatedUser>((resolve) => { complete = resolve; }));
    const auth = provider();
    const login = auth.login(profile.email, "test-only-password");
    const signal = harness.login.mock.calls[0][2] as AbortSignal;
    auth.logout();
    expect(signal.aborted).toBe(true);
    complete(profile);
    await expect(login).rejects.toMatchObject({ name: "AbortError" });
    expect(harness.setters[0]).not.toHaveBeenCalledWith(profile);
    expect(harness.clear).toHaveBeenCalledTimes(2);
  });
  it("clears the old role before login and publishes only the verified profile", async () => {
    harness.login.mockResolvedValue(profile);
    const auth = provider();
    await auth.login(profile.email, "test-only-password");
    expect(harness.setters[0].mock.calls).toEqual([[null], [profile]]);
    expect(harness.setters[1].mock.calls).toEqual([[true], [false]]);
    expect(harness.clear).toHaveBeenCalledOnce();
  });
  it("resets the shell for cross-tab token changes and aborts restoration on unmount", async () => {
    provider();
    const cleanup = harness.effects[0]();
    const firstSignal = harness.restore.mock.calls[0][0] as AbortSignal;
    const onStorage = harness.addEventListener.mock.calls[0][1] as (event: { key: string | null }) => void;
    onStorage({ key: "unrelated" });
    expect(harness.restore).toHaveBeenCalledOnce();
    onStorage({ key: AUTH_TOKEN_KEY });
    expect(firstSignal.aborted).toBe(true);
    expect(harness.clear).toHaveBeenCalledTimes(2);
    const latestSignal = harness.restore.mock.calls[1][0] as AbortSignal;
    if (typeof cleanup === "function") cleanup();
    expect(latestSignal.aborted).toBe(true);
    expect(harness.removeEventListener).toHaveBeenCalledWith("storage", onStorage);
    await flush();
    expect(harness.setters[0].mock.calls).toEqual([[null], [null]]);
  });
  it("does not delete a replacement token when restoration rejects", async () => {
    harness.restore.mockRejectedValue(new DOMException("Session changed", "AbortError"));
    provider();
    harness.effects[0]();
    await flush();
    expect(harness.remove).not.toHaveBeenCalled();
  });
});
