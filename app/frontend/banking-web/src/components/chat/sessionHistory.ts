import { z } from "zod";
import type { Thread, ThreadItem } from "./types";
import { disputePreviewSchema, supportCaseStatusSchema } from "@/api/supportCaseContracts";

export const CHAT_HISTORY_KEY = "banking-chat-session-v1";
const text = z.string().max(100000);
const identifier = z.string().min(1).max(200);
export const recordedDecisionSchema = z.object({ caseId: identifier.nullable(), declined: z.boolean(), status: supportCaseStatusSchema.optional() })
  .refine(value => value.declined ? value.caseId === null : Boolean(value.caseId?.trim()));
const pendingSchema = z.object({ scope: z.string(), threadId: identifier });
const message = z.discriminatedUnion("type", [
  z.object({ type: z.literal("user_message"), content: z.array(z.object({ type: z.literal("input_text"), text })).max(100), attachments: z.array(z.never()).max(0) }),
  z.object({ type: z.literal("assistant_message"), content: z.array(z.object({ type: z.literal("output_text"), text, annotations: z.array(z.never()).max(0) })).max(100), streaming: z.literal(false) }),
  z.object({ type: z.literal("client_widget"), name: z.enum(["dispute_preview", "dispute_consent"]), args: z.object({ caseId: identifier.optional(), recordedDecision: recordedDecisionSchema.optional(), recoveryOnly: z.literal(true).optional(), preview: disputePreviewSchema.optional() }) }),
]).refine(entry => entry.type !== "client_widget" || (entry.name === "dispute_consent" ? Boolean(entry.args.caseId) : Boolean(entry.args.recordedDecision && (entry.args.recordedDecision.declined ? entry.args.recordedDecision.caseId === null : entry.args.recordedDecision.caseId) || entry.args.recoveryOnly && entry.args.preview)));
const item = z.object({ id: z.string().max(200), thread_id: z.string().max(200), created_at: z.string().max(100) }).and(message);
const snapshotSchema = z.object({
  scope: z.string(), activeThreadId: z.string().nullable(),
  threads: z.array(z.object({ id: z.string().max(200), title: z.string().max(100).nullable(), created_at: z.string().max(100),
    status: z.object({ type: z.enum(["active", "locked", "closed"]) }),
    metadata: z.object({ conversationId: z.string().max(16000).optional(), furtherHelp: z.boolean().optional(), interrupted: z.boolean().optional() }),
  })).max(10),
  items: z.record(z.array(item).max(200)), completed: z.array(z.string().max(500)).max(2000),
});
export interface ChatSnapshot {
  scope: string;
  activeThreadId: string | null;
  threads: Thread[];
  items: Record<string, ThreadItem[]>;
  completed: string[];
}

// Write before starting transport so a reload cannot revive a stale checkpoint.
export function markChatInterrupted(scope: string, threadId: string): void {
  try {
    sessionStorage.setItem(`${CHAT_HISTORY_KEY}-pending`, JSON.stringify({ scope, threadId }));
  } catch {
    try { sessionStorage.removeItem(CHAT_HISTORY_KEY); } catch { /* Storage is optional. */ }
  }
}

export function visibleConversation(items: ThreadItem[]): { role: "user" | "assistant"; text: string }[] {
  const result: { role: "user" | "assistant"; text: string }[] = [];
  let remaining = 100000;
  for (const item of [...items].reverse()) {
    if (item.type !== "user_message" && item.type !== "assistant_message") continue;
    const content = item.content.filter(part => part.type === "input_text" || part.type === "output_text").map(part => part.text).join("\n");
    if (!content.trim()) continue;
    result.unshift({ role: item.type === "user_message" ? "user" : "assistant", text: content.slice(-remaining) });
    remaining -= Math.min(remaining, content.length);
    if (!remaining || result.length === 100) break;
  }
  return result;
}

export function readChatSnapshot(scope: string): ChatSnapshot | null {
  try {
    const raw = sessionStorage.getItem(CHAT_HISTORY_KEY);
    if (!raw) return null;
    const parsed = raw.length <= 2000000 ? snapshotSchema.safeParse(JSON.parse(raw)) : null;
    if (!parsed?.success || parsed.data.scope !== scope) { sessionStorage.removeItem(CHAT_HISTORY_KEY); return null; }
    const snapshot = parsed.data as ChatSnapshot;
    const ids = new Set(snapshot.threads.map(thread => thread.id));
    const references = new Set(Object.entries(snapshot.items).flatMap(([id, entries]) => entries.map(entry => `${id}:${entry.id}`)));
    if (ids.size !== snapshot.threads.length || (snapshot.activeThreadId !== null && !ids.has(snapshot.activeThreadId)) ||
      Object.entries(snapshot.items).some(([id, entries]) => !ids.has(id) || new Set(entries.map(entry => entry.id)).size !== entries.length || entries.some(entry => entry.thread_id !== id)) ||
      snapshot.completed.some(key => !references.has(key)) || new Set(snapshot.completed).size !== snapshot.completed.length) {
      sessionStorage.removeItem(CHAT_HISTORY_KEY);
      return null;
    }
    snapshot.threads = snapshot.threads.map(thread => thread.status.type === "active" && (snapshot.items[thread.id] ?? []).some(entry => entry.type === "client_widget" && !snapshot.completed.includes(`${thread.id}:${entry.id}`))
      ? { ...thread, status: { type: "locked" } } : thread);
    const pendingRaw = sessionStorage.getItem(`${CHAT_HISTORY_KEY}-pending`);
    if (pendingRaw) {
      if (pendingRaw.length > 20000) throw new Error("Invalid interruption marker");
      const pending = pendingSchema.parse(JSON.parse(pendingRaw));
      if (pending.scope === scope) snapshot.threads = snapshot.threads.map(thread => thread.id === pending.threadId && thread.status.type !== "closed"
        ? { ...thread, status: { type: "locked" } } : thread);
    }
    return snapshot;
  } catch {
    try { sessionStorage.removeItem(CHAT_HISTORY_KEY); } catch { /* Storage is optional. */ }
    return null;
  }
}

export function clearChatSnapshot(): void {
  try {
    sessionStorage.removeItem(CHAT_HISTORY_KEY);
    sessionStorage.removeItem(`${CHAT_HISTORY_KEY}-pending`);
  } catch { /* Storage is optional. */ }
}

export function persistChatSnapshot(scope: string, threads: Thread[], items: Record<string, ThreadItem[]>, activeThreadId: string | null, completed: Set<string>, blocked: Set<string>, streaming: string | null, requiredRecovery?: { threadId: string; itemId: string; previewToken: string }): boolean {
  try {
    const kept = threads.slice(0, 10);
    const snapshot: ChatSnapshot = {
      scope, activeThreadId: kept.some(thread => thread.id === activeThreadId) ? activeThreadId : null,
      threads: kept.map(thread => ({ ...thread,
        status: { type: thread.status.type === "closed" ? "closed" : blocked.has(thread.id) || streaming === thread.id || (items[thread.id] ?? []).some(entry => entry.type === "client_widget" && !completed.has(`${thread.id}:${entry.id}`)) ? "locked" : thread.status.type },
        metadata: { conversationId: typeof thread.metadata?.conversationId === "string" ? thread.metadata.conversationId : undefined, furtherHelp: thread.metadata?.furtherHelp === true, interrupted: thread.metadata?.interrupted === true },
      })),
      items: Object.fromEntries(kept.map(thread => [thread.id, (items[thread.id] ?? []).slice(-200).flatMap(entry => {
        let candidate: unknown = entry;
        if (entry.type === "client_widget") {
          if (entry.name === "dispute_preview" && entry.args?.recordedDecision) candidate = { ...entry, args: { recordedDecision: entry.args.recordedDecision } };
          else if (entry.name === "dispute_preview" && entry.args?.recoveryOnly === true) candidate = { ...entry, args: { recoveryOnly: true, preview: entry.args.preview } };
          else if (entry.name === "dispute_consent" && typeof entry.args?.caseId === "string") candidate = { ...entry, args: { caseId: entry.args.caseId } };
          else return [];
        }
        if (entry.type === "user_message") candidate = { ...entry, content: entry.content.filter(part => part.type === "input_text"), attachments: [] };
        if (entry.type === "assistant_message") candidate = { ...entry, streaming: false, content: entry.content.map(part => ({ ...part, annotations: [] })) };
        const parsed = item.safeParse(candidate);
        return parsed.success ? [parsed.data as ThreadItem] : [];
      })])),
      completed: [...completed].filter(key => kept.some(thread => key.startsWith(`${thread.id}:`))).slice(-2000),
    };
    const keptReferences = new Set(Object.entries(snapshot.items).flatMap(([id, entries]) => entries.map(entry => `${id}:${entry.id}`)));
    snapshot.completed = snapshot.completed.filter(key => keptReferences.has(key));
    if (requiredRecovery) {
      const evidence = snapshot.items[requiredRecovery.threadId]?.find(entry => entry.id === requiredRecovery.itemId);
      if (evidence?.type !== "client_widget" || evidence.args.recoveryOnly !== true ||
        (evidence.args.preview as { previewToken?: string } | undefined)?.previewToken !== requiredRecovery.previewToken) return false;
    }
    const encoded = JSON.stringify(snapshotSchema.parse(snapshot));
    if (encoded.length <= 2000000) {
      sessionStorage.setItem(CHAT_HISTORY_KEY, encoded);
      if (!streaming) sessionStorage.removeItem(`${CHAT_HISTORY_KEY}-pending`);
      return true;
    } else sessionStorage.removeItem(CHAT_HISTORY_KEY);
  } catch {
    try { sessionStorage.removeItem(CHAT_HISTORY_KEY); } catch { /* Storage can be disabled. */ }
  }
  return false;
}
