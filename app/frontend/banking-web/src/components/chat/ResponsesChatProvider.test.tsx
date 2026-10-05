import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatProvider } from "./ResponsesChatProvider";
import type { ChatContextValue, ThreadItem } from "./types";
import type { StreamEvent } from "./useThreadStream";
import en from "@/locales/en.json";
import es from "@/locales/es.json";
import pt from "@/locales/pt.json";

const h = vi.hoisted(() => ({
  slots: [] as unknown[], cursor: 0,
  effects: [] as Array<{ deps: unknown[]; cleanup?: () => void }>,
  queued: [] as Array<() => void>, cancel: vi.fn(),
  stream: null as unknown as Parameters<typeof import("./useThreadStream").useThreadStream>[0],
  catalog: {} as Record<string, string>,
}));
vi.mock("react", async original => ({
  ...await original<typeof import("react")>(),
  useState: (initial: unknown) => {
    const index = h.cursor++;
    if (!(index in h.slots)) h.slots[index] = typeof initial === "function" ? initial() : initial;
    return [h.slots[index], (next: unknown) => {
      h.slots[index] = typeof next === "function" ? next(h.slots[index]) : next;
    }];
  },
  useRef: (current: unknown) => h.slots[h.cursor++] ??= { current },
  useMemo: (factory: () => unknown) => factory(),
  useCallback: (callback: unknown) => callback,
  useEffect: (effect: () => void | (() => void), deps: unknown[]) => {
    const index = h.cursor++;
    const previous = h.effects[index];
    if (!previous || deps.some((dep, i) => dep !== previous.deps[i])) {
      h.queued.push(() => {
        previous?.cleanup?.();
        const cleanup = effect();
        h.effects[index] = { deps, cleanup: cleanup || undefined };
      });
    }
  },
}));
vi.mock("./useThreadStream", () => ({ useThreadStream: (options: typeof h.stream) => {
  h.stream = options;
  return { cancel: h.cancel };
} }));
vi.mock("@/components/chat/widgets", () => ({ widgetRegistry: { register: vi.fn() } }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => h.catalog[key] ?? key }) }));

const ended = vi.fn();
const errors = vi.fn();
function render(): ChatContextValue {
  h.cursor = 0;
  const value = ChatProvider({ children: null, onResponseEnd: ended, onError: errors }).props.value;
  h.queued.splice(0).forEach(effect => effect());
  return value;
}
function event(value: StreamEvent) { h.stream.onEvent?.(value); return render(); }
function finish() { h.stream.onComplete?.(); return render(); }
function start() { render().sendMessage("Review my transaction"); return render(); }
function tasks(value = render()) { return value.items.filter((item): item is Extract<ThreadItem, { type: "task" }> => item.type === "task"); }
function approval() {
  start();
  event({ type: "response.output_item.added", item: { type: "mcp_approval_request", id: "approval-1", name: "open_transaction_dispute", arguments: '{"transactionId":"tx-1"}' } });
  event({ type: "response.completed" });
  return finish();
}
function act(value = render(), approved = true) {
  return value.sendWidgetAction(value.activeThreadId!, "approval-1", { type: "approval", payload: { approved } });
}

beforeEach(() => {
  vi.clearAllMocks(); h.slots = []; h.effects = []; h.queued = []; h.catalog = {};
});

describe("Responses provider tool progress", () => {
  it("correlates a result by call_id rather than its different output item id", () => {
    start();
    event({ type: "response.output_item.added", item: { type: "function_call", id: "declaration-1", call_id: "call-1", name: "get_transactions" } });
    expect(tasks()[0].task).toMatchObject({ title: "Looking up transactions", status_indicator: "loading" });
    event({ type: "response.output_item.done", item: { type: "function_call_output", id: "result-1", call_id: "call-1", output: "[]" } });
    expect(tasks()).toHaveLength(0);
  });
  it("does not treat declarations, outputless completion or unrelated results as success", () => {
    start();
    event({ type: "response.output_item.added", item: { type: "mcp_call", id: "call-1", name: "get_balance" } });
    event({ type: "response.output_item.done", item: { type: "mcp_call", id: "call-1", name: "get_balance" } });
    event({ type: "response.output_item.done", item: { type: "function_call_output", call_id: "other-call", output: "{}" } });
    expect(tasks()[0].task.status_indicator).toBe("loading");
    finish();
    expect(tasks()[0].task).toMatchObject({ title: "Tool result unavailable", status_indicator: "none" });
  });
  it("deduplicates added/done events and keeps concurrent calls independent", () => {
    start();
    const added = { type: "response.output_item.added", item: { type: "function_call", id: "decl", call_id: "one", name: "get_transactions" } };
    event(added); event(added);
    event({ type: "response.output_item.added", item: { type: "function_call", call_id: "two", name: "get_balance" } });
    const done = { type: "response.output_item.done", item: { type: "function_call_output", call_id: "one", output: "[]" } };
    event(done); event(done);
    expect(tasks()).toHaveLength(1);
    expect(tasks()[0].task).toMatchObject({ title: "Looking up account information", status_indicator: "loading" });
    finish();
    expect(tasks().map(item => item.task.title)).toEqual(["Tool result unavailable"]);
  });
  it("retains failed tool feedback without completing a concurrent pending call", () => {
    start();
    event({ type: "response.output_item.added", item: { type: "function_call", call_id: "failed", name: "get_transactions" } });
    event({ type: "response.output_item.added", item: { type: "function_call", call_id: "pending", name: "get_balance" } });
    event({ type: "response.output_item.done", item: { type: "function_call_output", call_id: "failed", error: "private failure" } });
    expect(tasks().map(item => item.task)).toEqual([
      expect.objectContaining({ title: "Tool result unavailable", status_indicator: "none" }),
      expect.objectContaining({ title: "Looking up account information", status_indicator: "loading" }),
    ]);
    event({ type: "response.output_item.done", item: { type: "function_call_output", call_id: "pending", output: "{}" } });
    expect(tasks()).toHaveLength(1);
    expect(tasks()[0].task).toMatchObject({ title: "Tool result unavailable", status_indicator: "none" });
  });
  it("ignores handoff declarations and clears correlation state for the next stream", () => {
    start();
    event({ type: "response.output_item.added", item: { type: "function_call", call_id: "handoff", name: "transfer_to_transaction" } });
    expect(tasks()).toEqual([]);
    event({ type: "response.output_item.added", item: { type: "mcp_call", id: "reused", name: "get_balance" } });
    finish();
    render().sendMessage("Try again"); render();
    event({ type: "response.output_item.added", item: { type: "mcp_call", id: "reused", name: "get_balance" } });
    expect(tasks()).toHaveLength(1);
    expect(tasks()[0].task.status_indicator).toBe("loading");
  });
  it.each(["complete", "error", "cancel"])("clears pending tasks and assistant streaming on %s", mode => {
    start();
    event({ type: "response.output_text.delta", delta: "Working" });
    event({ type: "response.output_item.added", item: { type: "mcp_call", id: "pending", name: "get_balance" } });
    if (mode === "cancel") render().cancelStreaming();
    else if (mode === "error") h.stream.onError?.(new Error("private failure"));
    else { event({ type: "response.completed" }); finish(); }
    const value = render();
    expect(value.isStreaming).toBe(false);
    expect(h.stream.request).toBeNull();
    expect(tasks()[0].task.status_indicator).toBe("none");
    expect(value.items.find(item => item.type === "assistant_message")).toMatchObject({ streaming: false });
    expect(ended).toHaveBeenCalledOnce();
  });
});

describe("Responses provider visible output", () => {
  const failureText = "The response could not be completed.";
  const errorItems = () => render().items.filter(item => item.type === "error");
  const messages = () => render().items.filter(item => item.type === "assistant_message");

  it.each([
    ["en", en, "The response could not be completed."],
    ["es", es, "No se pudo completar la respuesta."],
    ["pt", pt, "Não foi possível concluir a resposta."],
  ] as const)("renders a controlled %s failure for a handoff-only completed turn", (_locale, catalog, message) => {
    h.catalog = catalog;
    start();
    event({ type: "response.output_item.added", item: { type: "function_call", id: "handoff", call_id: "transfer", name: "handoff_to_transaction" } });
    event({ type: "response.output_item.done", item: { type: "function_call_output", call_id: "transfer", output: "private handoff receipt" } });
    event({ type: "response.completed" });
    finish(); finish();
    expect(errorItems()).toHaveLength(1);
    expect(errorItems()[0]).toMatchObject({ message, code: "SERVICE_UNAVAILABLE", allow_retry: true });
    expect(errors).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ message }));
    expect(ended).toHaveBeenCalledOnce();
    expect(render().isStreaming).toBe(false);
    expect(h.stream.request).toBeNull();
    expect(tasks()).toEqual([]);
  });

  it.each(["incomplete", "eof", "whitespace", "tool-progress"])("renders one visible failure for outputless %s", mode => {
    start();
    if (mode === "incomplete") event({ type: "response.incomplete" });
    if (mode === "whitespace") {
      event({ type: "response.output_text.delta", item_id: "blank", delta: " \n " });
      event({ type: "response.completed" });
    }
    if (mode === "tool-progress") {
      event({ type: "response.output_item.added", item: { type: "mcp_call", id: "tool", name: "get_balance" } });
      event({ type: "response.output_item.done", item: { type: "mcp_call", id: "tool", output: "{}" } });
      event({ type: "response.completed" });
    }
    finish(); finish();
    expect(errorItems()).toHaveLength(1);
    expect(errorItems()[0]).toMatchObject({ message: failureText, allow_retry: true });
    expect(messages().every(item => !item.streaming)).toBe(true);
    expect(ended).toHaveBeenCalledOnce();
  });

  it("does not request persisted consent for an accepted IN_REVIEW case", () => {
    start();
    event({ type: "response.output_item.done", item: { type: "mcp_call", name: "reportTransactionDispute", output: {
      caseId: "accepted-case", transactionId: "transaction", productNumber: null,
      reason: "Customer reason", status: "IN_REVIEW", triageOutcome: null,
      resolutionOutcome: null, resolutionNotes: null, recommendationType: null,
      recommendationRationale: null, recommendationOptedOut: false,
      openedAt: "2026-10-04", updatedAt: "2026-10-04", resolvedAt: null,
    } } });
    event({ type: "response.completed" }); finish();
    expect(render().items.filter(item => item.type === "client_widget" && item.name === "dispute_consent")).toEqual([]);
    expect(errorItems()).toEqual([]);
  });

  it("preserves approval-only and persisted consent-only completed turns", () => {
    approval();
    expect(errorItems()).toEqual([]);
    render().sendMessage("Continue"); render();
    event({ type: "response.output_item.done", item: { type: "mcp_call", output: {
      caseId: "owned-case", transactionId: "transaction", productNumber: null,
      reason: "Customer reason", status: "WAITING_USER_APPROVAL", triageOutcome: null,
      resolutionOutcome: null, resolutionNotes: null, recommendationType: null,
      recommendationRationale: null, recommendationOptedOut: false,
      openedAt: "2026-10-04", updatedAt: "2026-10-04", resolvedAt: null,
    } } });
    event({ type: "response.completed" }); finish();
    expect(errorItems()).toEqual([]);
    expect(render().items).toContainEqual(expect.objectContaining({ type: "client_widget", name: "dispute_consent", args: { caseId: "owned-case" } }));
    render().sendMessage("Another turn"); render();
    event({ type: "response.completed" }); finish();
    expect(errorItems()).toHaveLength(1);
  });

  it("does not add a fallback after cancellation or duplicate explicit failures", () => {
    start(); render().cancelStreaming(); finish();
    expect(errorItems()).toEqual([]);
    render().sendMessage("Retry"); render();
    event({ type: "response.failed", response: { error: { message: "private", code: "private" } } });
    event({ type: "response.failed" }); finish();
    expect(errorItems()).toHaveLength(1);
    expect(errorItems()[0]).toMatchObject({ message: failureText });
    expect(errors).toHaveBeenCalledOnce();
  });

  it("correlates interleaved assistant items and message IDs, retaining the no-ID fallback", () => {
    start();
    event({ type: "response.output_text.delta", item_id: "one", delta: "First" });
    event({ type: "response.output_text.delta", item_id: "two", delta: "Second" });
    event({ type: "response.output_text.delta", item_id: "one", delta: " answer" });
    event({ type: "response.output_text.delta", message_id: "three", delta: "Third" });
    event({ type: "response.output_text.delta", message_id: "three", delta: " answer" });
    event({ type: "response.output_text.delta", delta: "Fallback" });
    event({ type: "response.output_text.delta", delta: " answer" });
    event({ type: "response.output_text.delta", item_id: "fallback", delta: "Distinct" });
    event({ type: "response.completed" }); finish();
    expect(messages().map(item => item.content[0].text)).toEqual(["First answer", "Second", "Third answer", "Fallback answer", "Distinct"]);
    expect(messages().every(item => !item.streaming)).toBe(true);
    expect(errorItems()).toEqual([]);
    render().sendMessage("Next"); render();
    event({ type: "response.output_text.delta", item_id: "one", delta: "New answer" });
    event({ type: "response.completed" }); finish();
    expect(messages().map(item => item.content[0].text)).toEqual(["First answer", "Second", "Third answer", "Fallback answer", "Distinct", "New answer"]);
  });

  it("keeps an outputless completed approval continuation retryable", async () => {
    const value = approval();
    const result = act(value); render();
    event({ type: "response.completed" }); finish();
    await expect(result).resolves.toBe("error");
    expect(errorItems()).toHaveLength(1);
    expect(render().isApprovalCompleted(value.activeThreadId!, "approval-1")).toBe(false);
    const retry = act(); render();
    event({ type: "response.output_text.delta", delta: "Processed" });
    event({ type: "response.completed" }); finish();
    await expect(retry).resolves.toBe("success");
  });
});

describe("Responses dispute preview lifecycle", () => {
  const preview = { previewToken: "signed", transactionId: "tx", reason: "Original reason", expiresAt: "2026-10-04T10:10:00Z", transaction: { id: "tx", country: "CO", city: null } };
  function proposal() {
    start();
    event({ type: "response.output_item.added", item: { type: "function_call", call_id: "preview-call", name: "previewTransactionDispute" } });
    const done = { type: "response.output_item.done", item: { type: "function_call_output", call_id: "preview-call", output: preview } };
    event(done); event(done);
    event({ type: "response.completed" }); finish();
    return render().items.find(item => item.type === "client_widget" && item.name === "dispute_preview")!;
  }
  it("deduplicates correlated previews and never renders uncorrelated receipts", () => {
    start();
    event({ type: "response.output_item.done", item: { type: "function_call_output", call_id: "unknown", output: preview } });
    expect(render().items.filter(item => item.type === "client_widget")).toHaveLength(0);
    finish();
    const widget = proposal();
    expect(widget).toMatchObject({ args: { preview } });
    expect(render().items.filter(item => item.type === "client_widget")).toHaveLength(1);
  });
  it.each([true, false])("continues an explicit decision (%s) without repeating creation", async declined => {
    const widget = proposal();
    const value = render();
    const action = { type: "dispute_preview_decision", payload: { declined, caseId: declined ? null : "recorded-case" } };
    const result = value.sendWidgetAction(value.activeThreadId!, widget.id, action); render();
    const payload = h.stream.request?.payload as { input: Array<{ role: string; content: Array<{ text: string }> }> };
    expect(payload.input[0].role).toBe("user");
    expect(payload.input[0].content[0].text).toContain(declined ? "Do not create a support case" : "already recorded support case recorded-case");
    expect(JSON.stringify(payload)).not.toContain("mcp_approval_response");
    event({ type: "response.output_text.delta", delta: "Acknowledged" });
    event({ type: "response.completed" }); finish();
    await expect(result).resolves.toBe("success");
    await expect(render().sendWidgetAction(value.activeThreadId!, widget.id, action)).resolves.toBe("success");
    expect(h.stream.request).toBeNull();
  });
  it("permits continuation-only retry after failure", async () => {
    const widget = proposal(); const value = render();
    const action = { type: "dispute_preview_decision", payload: { declined: false, caseId: "recorded-case" } };
    const result = value.sendWidgetAction(value.activeThreadId!, widget.id, action); render();
    h.stream.onError?.(new Error("private")); finish();
    await expect(result).resolves.toBe("error");
    const retry = render().sendWidgetAction(value.activeThreadId!, widget.id, action); render();
    expect(JSON.stringify(h.stream.request?.payload)).toContain("already recorded support case recorded-case");
    event({ type: "response.output_text.delta", delta: "Acknowledged" }); event({ type: "response.completed" }); finish();
    await expect(retry).resolves.toBe("success");
  });
});

describe("Responses provider approval lifecycle", () => {
  it("settles only after completed stream cleanup, persists success and deduplicates replay", async () => {
    const value = approval(); ended.mockClear();
    const settled = vi.fn(); const result = act(value).then(settled); render();
    expect(h.stream.request?.payload).toMatchObject({ input: [{ type: "mcp_approval_response", approval_request_id: "approval-1", approve: true }] });
    await Promise.resolve(); expect(settled).not.toHaveBeenCalled();
    event({ type: "response.output_text.delta", delta: "Request processed" });
    event({ type: "response.completed" });
    await Promise.resolve(); expect(settled).not.toHaveBeenCalled();
    finish(); finish(); await result;
    expect(settled).toHaveBeenCalledExactlyOnceWith("success");
    expect(ended).toHaveBeenCalledOnce();
    expect(render().isApprovalCompleted(value.activeThreadId!, "approval-1")).toBe(true);
    await expect(act()).resolves.toBe("success");
    expect(render().isStreaming).toBe(false);
    expect(h.stream.request).toBeNull();
  });
  it.each(["error", "failed", "incomplete", "eof", "tool-error", "outputless-tool-error", "cancel"])("settles %s exactly once without consuming approval and permits retry", async mode => {
    const value = approval(); ended.mockClear();
    const settled = vi.fn(); const result = act(value).then(settled); render();
    if (mode === "error") h.stream.onError?.(new Error("private"));
    else if (mode === "cancel") render().cancelStreaming();
    else {
      if (mode === "failed") event({ type: "response.failed", response: { error: { message: "private", code: "private" } } });
      if (mode === "incomplete") event({ type: "response.incomplete" });
      if (mode === "tool-error") event({ type: "response.output_item.done", item: { type: "mcp_call", output: { isError: true } } });
      if (mode === "outputless-tool-error") event({ type: "response.output_item.done", item: { type: "mcp_call", error: { code: "tool_failed" } } });
      if (mode !== "eof") event({ type: "response.completed" });
      finish();
    }
    finish(); await result;
    expect(settled).toHaveBeenCalledExactlyOnceWith(mode === "cancel" ? "cancelled" : "error");
    expect(ended).toHaveBeenCalledOnce();
    expect(render().isApprovalCompleted(value.activeThreadId!, "approval-1")).toBe(false);
    const retry = act(render(), false); render();
    expect(h.stream.request?.payload).toMatchObject({ input: [{ type: "mcp_approval_response", approval_request_id: "approval-1", approve: false }] });
    event({ type: "response.output_text.delta", delta: "Request declined" });
    event({ type: "response.completed" }); finish();
    await expect(retry).resolves.toBe("success");
  });
  it("rejects synchronous duplicate submissions without replacing the first promise", async () => {
    const value = approval();
    const first = act(value); const duplicate = act(value, false); render();
    await expect(duplicate).resolves.toBe("error");
    event({ type: "response.output_text.delta", delta: "Request processed" });
    event({ type: "response.completed" }); finish();
    await expect(first).resolves.toBe("success");
  });
  it("settles pending action as cancelled once on unmount", async () => {
    approval(); const settled = vi.fn(); const result = act().then(settled); render();
    h.effects.forEach(effect => effect?.cleanup?.());
    h.effects.forEach(effect => effect?.cleanup?.());
    await result;
    expect(settled).toHaveBeenCalledExactlyOnceWith("cancelled");
  });
  it("deduplicates approval declarations and refuses unknown widgets", async () => {
    const value = approval();
    render().sendMessage("Continue"); render();
    event({ type: "response.output_item.done", item: { type: "mcp_approval_request", id: "approval-1", name: "open_transaction_dispute" } });
    finish();
    expect(render().items.filter(item => item.id === "approval-1")).toHaveLength(1);
    await expect(render().sendWidgetAction(value.activeThreadId!, "unknown", { type: "approval" })).resolves.toBe("error");
    expect(render().isStreaming).toBe(false);
  });
});
