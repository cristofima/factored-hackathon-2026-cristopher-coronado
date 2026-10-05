import { beforeEach, describe, expect, it, vi } from "vitest";
import { CHAT_HISTORY_KEY, markChatInterrupted, persistChatSnapshot, readChatSnapshot, visibleConversation } from "./sessionHistory";
import type { Thread, ThreadItem } from "./types";

const scope = JSON.stringify(["customer", 1, 1, "/responses"]);
const thread: Thread = { id: "thread", title: "Conversation", created_at: "2026-10-04", status: { type: "active" }, metadata: { conversationId: "signed-continuation", secret: "metadata-secret" } };
const message = (id: string, text: string): ThreadItem => ({ id, thread_id: "thread", created_at: "2026-10-04", type: "user_message", content: [{ type: "input_text", text }], attachments: [] });
function save(items: ThreadItem[] = [message("user", "Visible question")], completed = new Set<string>(), streaming: string | null = null) {
  persistChatSnapshot(scope, [thread], { thread: items }, "thread", completed, new Set(), streaming);
}
beforeEach(() => {
  const storage = new Map<string, string>();
  vi.stubGlobal("sessionStorage", { getItem: (key: string) => storage.get(key) ?? null, setItem: (key: string, value: string) => storage.set(key, value), removeItem: (key: string) => storage.delete(key) });
});

describe("session chat checkpoints", () => {
  it("recovers visible history and signed continuation only in the same scope", () => {
    save();
    expect(readChatSnapshot(scope)).toMatchObject({ activeThreadId: "thread", threads: [{ metadata: { conversationId: "signed-continuation" }, status: { type: "active" } }], items: { thread: [{ id: "user" }] } });
    expect(sessionStorage.getItem(CHAT_HISTORY_KEY)).not.toContain("metadata-secret");
    expect(readChatSnapshot(JSON.stringify(["customer", 2, 1, "/responses"]))).toBeNull();
    expect(sessionStorage.getItem(CHAT_HISTORY_KEY)).toBeNull();
  });
  it("locks a stale checkpoint when transport was interrupted before a render", () => {
    save(); markChatInterrupted(scope, "thread");
    expect(readChatSnapshot(scope)?.threads[0].status.type).toBe("locked");
  });
  it("locks streaming and incomplete widget recovery but preserves completed receipts", () => {
    const receipt: ThreadItem = { id: "proposal", thread_id: "thread", created_at: "2026-10-04", type: "client_widget", name: "dispute_preview", args: { previewToken: "must-not-persist", recordedDecision: { caseId: "case", declined: false } } };
    save([receipt]); expect(readChatSnapshot(scope)?.threads[0].status.type).toBe("locked");
    save([receipt], new Set(["thread:proposal", "thread:dropped"]));
    expect(readChatSnapshot(scope)?.threads[0].status.type).toBe("active");
    expect(readChatSnapshot(scope)?.completed).toEqual(["thread:proposal"]);
    expect(sessionStorage.getItem(CHAT_HISTORY_KEY)).not.toContain("must-not-persist");
    save([message("user", "Question")], new Set(), "thread");
    expect(readChatSnapshot(scope)?.threads[0].status.type).toBe("locked");
  });
  it.each(["invalid-json", "oversized", "duplicate-items", "missing-reference", "bad-marker", "invalid-receipt"])("rejects %s rather than enabling continuation", kind => {
    save();
    const raw = JSON.parse(sessionStorage.getItem(CHAT_HISTORY_KEY)!);
    if (kind === "duplicate-items") raw.items.thread.push(raw.items.thread[0]);
    if (kind === "missing-reference") raw.completed = ["thread:missing"];
    if (kind === "invalid-receipt") raw.items.thread = [{ id: "proposal", thread_id: "thread", created_at: "today", type: "client_widget", name: "dispute_preview", args: { recordedDecision: { caseId: null, declined: false } } }];
    sessionStorage.setItem(CHAT_HISTORY_KEY, kind === "invalid-json" ? "{" : kind === "oversized" ? "x".repeat(2000001) : JSON.stringify(raw));
    if (kind === "bad-marker") sessionStorage.setItem(`${CHAT_HISTORY_KEY}-pending`, "{}");
    expect(readChatSnapshot(scope)).toBeNull();
  });
  it("strips tool/task entries, tags and attachments from persistence", () => {
    const user = message("user", "Visible");
    if (user.type !== "user_message") throw new Error("Expected message");
    user.content.push({ type: "input_tag", id: "tag", text: "hidden-tag", data: { token: "tag-secret" }, group: null, interactive: false });
    user.attachments = [{ type: "file", id: "file", name: "attachment-secret", mime_type: "text/plain" }];
    const tool: ThreadItem = { id: "tool", thread_id: "thread", created_at: "today", type: "client_widget", name: "tool_approval_request", args: { token: "tool-secret" } };
    save([user, tool]);
    const raw = sessionStorage.getItem(CHAT_HISTORY_KEY)!;
    expect(raw).not.toMatch(/tag-secret|hidden-tag|attachment-secret|tool-secret/);
    expect(readChatSnapshot(scope)?.items.thread).toHaveLength(1);
    expect(readChatSnapshot(scope)?.threads[0].status.type).toBe("locked");
  });
});

describe("required preview recovery durability", () => {
  const preview = { previewToken: "signed-recovery", transactionId: "tx", reason: "Customer reason", expiresAt: "2026-10-04T10:10:00Z", transaction: { id: "tx" } };
  const evidence: ThreadItem = { id: "preview", thread_id: "thread", created_at: "2026-10-04", type: "client_widget", name: "dispute_preview", args: { recoveryOnly: true, preview, hidden: "not-retained" } };
  const required = { threadId: "thread", itemId: "preview", previewToken: preview.previewToken };
  function persist(items: ThreadItem[], threads = [thread], requirement = required) {
    return persistChatSnapshot(scope, threads, { thread: items }, "thread", new Set(), new Set(["thread"]), null, requirement);
  }
  it("retains exact recovery evidence and clears the pending marker only after saving", () => {
    save(); markChatInterrupted(scope, "thread");
    expect(persist([evidence])).toBe(true);
    expect(sessionStorage.getItem(`${CHAT_HISTORY_KEY}-pending`)).toBeNull();
    expect(readChatSnapshot(scope)).toMatchObject({ threads: [{ status: { type: "locked" } }], items: { thread: [{ id: "preview", args: { recoveryOnly: true, preview } }] } });
    expect(sessionStorage.getItem(CHAT_HISTORY_KEY)).not.toContain("not-retained");
  });
  it.each(["missing-item", "missing-thread", "wrong-token", "unmarked", "malformed", "recorded", "item-truncated", "thread-truncated"])("rejects %s required evidence without claiming a durable write", kind => {
    save(); markChatInterrupted(scope, "thread");
    const prior = sessionStorage.getItem(CHAT_HISTORY_KEY);
    let items: ThreadItem[] = [evidence]; let threads = [thread]; let requirement = required;
    if (kind === "missing-item") requirement = { ...required, itemId: "missing" };
    if (kind === "missing-thread") requirement = { ...required, threadId: "missing" };
    if (kind === "wrong-token") requirement = { ...required, previewToken: "different-token" };
    if (kind === "unmarked") items = [{ ...evidence, args: { preview } } as ThreadItem];
    if (kind === "malformed") items = [{ ...evidence, args: { recoveryOnly: true, preview: { ...preview, transaction: { id: "other" } } } } as ThreadItem];
    if (kind === "recorded") items = [{ ...evidence, args: { recoveryOnly: true, preview, recordedDecision: { caseId: "case", declined: false } } } as ThreadItem];
    if (kind === "item-truncated") items = [evidence, ...Array.from({ length: 200 }, (_, index) => message(`user-${index}`, "Visible"))];
    if (kind === "thread-truncated") threads = [...Array.from({ length: 10 }, (_, index): Thread => ({ ...thread, id: `other-${index}` })), thread];
    expect(persist(items, threads, requirement)).toBe(false);
    expect(sessionStorage.getItem(CHAT_HISTORY_KEY)).toBe(prior);
    expect(sessionStorage.getItem(`${CHAT_HISTORY_KEY}-pending`)).not.toBeNull();
    expect(readChatSnapshot(scope)?.threads[0].status.type).toBe("locked");
  });
  it("rejects oversized recovery snapshots and removes stale history without clearing the interruption marker", () => {
    save(); markChatInterrupted(scope, "thread");
    expect(persist([...Array.from({ length: 21 }, (_, index) => message(`large-${index}`, "x".repeat(100000))), evidence])).toBe(false);
    expect(sessionStorage.getItem(CHAT_HISTORY_KEY)).toBeNull();
    expect(sessionStorage.getItem(`${CHAT_HISTORY_KEY}-pending`)).not.toBeNull();
  });
  it.each(["write", "pending-cleanup", "all-storage"])("returns false when %s fails and never exposes an active stale checkpoint", kind => {
    save(); markChatInterrupted(scope, "thread");
    const remove = sessionStorage.removeItem.bind(sessionStorage);
    if (kind !== "pending-cleanup") vi.spyOn(sessionStorage, "setItem").mockImplementation(() => { throw new Error("Storage denied"); });
    if (kind !== "write") vi.spyOn(sessionStorage, "removeItem").mockImplementation(key => {
      if (kind === "all-storage" || key === `${CHAT_HISTORY_KEY}-pending`) throw new Error("Storage denied");
      remove(key);
    });
    expect(persist([evidence])).toBe(false);
    expect(sessionStorage.getItem(`${CHAT_HISTORY_KEY}-pending`)).not.toBeNull();
    if (kind === "all-storage") expect(readChatSnapshot(scope)?.threads[0].status.type).toBe("locked");
    else expect(readChatSnapshot(scope)).toBeNull();
  });
});

describe("visible intake transcript", () => {
  it("keeps the newest 100 messages in chronological order", () => {
    const result = visibleConversation(Array.from({ length: 110 }, (_, index) => message(String(index), String(index))));
    expect(result).toHaveLength(100); expect(result[0].text).toBe("10"); expect(result[99].text).toBe("109");
  });
  it("bounds total characters and excludes widgets and nontext tags", () => {
    const result = visibleConversation([message("old", "a".repeat(90000)), message("new", "b".repeat(90000))]);
    expect(result.map(entry => entry.text.length)).toEqual([10000, 90000]);
    expect(result.every(entry => entry.role === "user")).toBe(true);
  });
});
