import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useThreadStream, type StreamEvent } from "./useThreadStream";

const harness = vi.hoisted(() => ({
  effects: [] as Array<() => void | (() => void)>,
  refs: [] as Array<{ current: unknown }>, index: 0,
  token: "customer-token", fetch: vi.fn(),
}));
vi.mock("react", () => ({
  useEffect: (effect: () => void | (() => void)) => harness.effects.push(effect),
  useRef: (current: unknown) => {
    const index = harness.index++;
    return harness.refs[index] ??= { current };
  },
}));
vi.mock("@/api/authToken", () => ({ getAuthToken: () => harness.token }));
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
const useStreamHarness = (callbacks = { onEvent: vi.fn(), onConversation: vi.fn(), onError: vi.fn(), onComplete: vi.fn() }) => {
  harness.index = 0;
  const firstEffect = harness.effects.length;
  const result = useThreadStream({ url: "/responses", request: { threadId: "local-thread", payload: { input: "hello" } }, enabled: true, ...callbacks });
  harness.effects[firstEffect]();
  const cleanup = harness.effects[firstEffect + 1]();
  return { ...result, ...callbacks, cleanup };
};
const success = (reader: { read: () => Promise<ReadableStreamReadResult<Uint8Array>> }) => ({
  ok: true, headers: new Headers({ "X-Conversation-Id": "conversation" }), body: { getReader: () => reader },
});
beforeEach(() => {
  vi.clearAllMocks();
  harness.effects.length = 0;
  harness.refs.length = 0;
  harness.token = "customer-token";
  vi.stubGlobal("fetch", harness.fetch);
});
afterEach(() => vi.unstubAllGlobals());

describe("customer stream session isolation", () => {
  it("sends the application bearer through the BFF and forwards a controlled revocation error", async () => {
    harness.fetch.mockResolvedValue({ ok: false, status: 401, json: async () => ({ detail: { code: "AUTH_REQUIRED" } }) });
    const stream = useStreamHarness();
    await flush();
    expect(harness.fetch).toHaveBeenCalledWith("/responses", expect.objectContaining({
      headers: expect.objectContaining({ Authorization: "Bearer customer-token" }),
      body: JSON.stringify({ input: "hello" }),
    }));
    expect(stream.onEvent).toHaveBeenCalledWith(expect.objectContaining({ type: "error", code: "AUTH_REQUIRED", allow_retry: false }));
    expect(stream.onComplete).toHaveBeenCalledOnce();
  });
  it.each(["cancel", "unmount", "token-switch"])("ignores late conversation and callbacks after %s", async (mode) => {
    const response = deferred<unknown>();
    harness.fetch.mockReturnValue(response.promise);
    const stream = useStreamHarness();
    if (mode === "cancel") stream.cancel();
    if (mode === "unmount" && typeof stream.cleanup === "function") stream.cleanup();
    if (mode === "token-switch") harness.token = "staff-token";
    const read = vi.fn().mockResolvedValue({ done: true });
    response.resolve(success({ read }));
    await flush();
    expect(read).not.toHaveBeenCalled();
    expect(stream.onConversation).not.toHaveBeenCalled();
    expect(stream.onEvent).not.toHaveBeenCalled();
    expect(stream.onComplete).not.toHaveBeenCalled();
    expect(stream.onError).not.toHaveBeenCalled();
  });
  it.each<StreamEvent>([
    { type: "response.output_text.delta", delta: "old answer" },
    { type: "response.output_item.added", item: { type: "mcp_approval_request", id: "old-approval" } },
  ])("ignores late $type chunks after cancellation", async (event) => {
    const chunk = deferred<ReadableStreamReadResult<Uint8Array>>();
    harness.fetch.mockResolvedValue(success({ read: () => chunk.promise }));
    const stream = useStreamHarness();
    await flush();
    stream.cancel();
    chunk.resolve({ done: false, value: new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`) });
    await flush();
    expect(stream.onEvent).not.toHaveBeenCalled();
    expect(stream.onComplete).not.toHaveBeenCalled();
  });
  it("does not route an old rejected request into replacement callbacks", async () => {
    const old = deferred<unknown>();
    const next = deferred<unknown>();
    harness.fetch.mockReturnValueOnce(old.promise).mockReturnValueOnce(next.promise);
    const first = useStreamHarness();
    if (typeof first.cleanup === "function") first.cleanup();
    const second = useStreamHarness();
    old.reject(new Error("Old transport failure"));
    await flush();
    expect(first.onError).not.toHaveBeenCalled();
    expect(second.onError).not.toHaveBeenCalled();
    expect((harness.fetch.mock.calls[1][1].signal as AbortSignal).aborted).toBe(false);
    second.cancel();
    next.resolve(success({ read: vi.fn() }));
    await flush();
  });
  it("ignores revocation returned by an old token after a new login", async () => {
    const body = deferred<unknown>();
    harness.fetch.mockResolvedValue({ ok: false, status: 401, json: () => body.promise });
    const stream = useStreamHarness();
    await flush();
    harness.token = "new-customer-token";
    body.resolve({ detail: { code: "AUTH_REQUIRED" } });
    await flush();
    expect(stream.onEvent).not.toHaveBeenCalled();
    expect(stream.onComplete).not.toHaveBeenCalled();
  });
  it("forwards current conversation, text, approval and completion", async () => {
    const events = [{ type: "response.output_text.delta", delta: "current answer" }, { type: "response.output_item.added", item: { type: "mcp_approval_request", id: "current-approval" } }];
    const read = vi.fn().mockResolvedValueOnce({ done: false, value: new TextEncoder().encode(events.map((event) => `data: ${JSON.stringify(event)}\n`).join("")) }).mockResolvedValueOnce({ done: true });
    harness.fetch.mockResolvedValue(success({ read }));
    const stream = useStreamHarness();
    await flush();
    expect(stream.onConversation).toHaveBeenCalledWith("local-thread", "conversation");
    expect(stream.onEvent.mock.calls.map(([event]) => event)).toEqual(events);
    expect(stream.onComplete).toHaveBeenCalledOnce();
  });
});
