import { isValidElement, type ReactElement, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DisputePreview } from "./DisputePreview";
import { DisputePreviewConsent } from "@/components/DisputePreviewConsent";

const h = vi.hoisted(() => ({ cursor: 0, states: [] as unknown[], refs: [] as Array<{ current: unknown }>, thread: "original", items: [] as import("../../types").ThreadItem[], locked: false, streaming: false, send: vi.fn() }));
vi.mock("react", async original => ({
  ...await original<typeof import("react")>(),
  useState: (initial: unknown) => {
    const index = h.cursor++;
    if (!(index in h.states)) h.states[index] = initial;
    return [h.states[index], (value: unknown) => { h.states[index] = value; }];
  },
  useRef: (initial: unknown) => h.refs[h.cursor++] ??= { current: initial },
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../ResponsesChatProvider", () => ({ useChat: () => ({ activeThreadId: h.thread, items: h.items, isThreadLocked: () => h.locked, isStreaming: h.streaming, sendWidgetAction: h.send }) }));
const preview = { previewToken: "signed", transactionId: "tx", reason: "Original reason", expiresAt: "2026-10-04T10:10:00Z", transaction: { id: "tx" } };
type Element = ReactElement<Record<string, unknown>>;
function elements(node: ReactNode): Element[] {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!isValidElement<Record<string, unknown>>(node)) return [];
  return [node, ...elements(node.props.children as ReactNode)];
}
function render(args = { preview }) { h.cursor = 0; return DisputePreview({ args, itemId: "proposal" }); }
function consent() { return elements(render()).find(element => element.type === DisputePreviewConsent)!; }
async function settle() { for (let i = 0; i < 12; i++) await Promise.resolve(); }
beforeEach(() => { h.cursor = 0; h.states = []; h.refs = []; h.thread = "original"; h.items = []; h.locked = false; h.streaming = false; h.send.mockReset().mockResolvedValue("success"); });

describe("chat dispute preview", () => {
  it.each([true, false])("continues a recorded decision (%s) without exposing the preview token", async declined => {
    const control = consent();
    if (declined) (control.props.onDeclined as () => void)();
    else (control.props.onAccepted as (value: unknown) => void)({ caseId: "recorded" });
    await settle();
    expect(h.send).toHaveBeenCalledWith("original", "proposal", { type: "dispute_preview_decision", payload: { caseId: declined ? null : "recorded", declined } });
    expect(JSON.stringify(h.send.mock.calls)).not.toContain("signed");
  });
  it("offers continuation-only retry after an error without repeating consent", async () => {
    h.send.mockResolvedValueOnce("error");
    (consent().props.onAccepted as (value: unknown) => void)({ caseId: "recorded" }); await settle();
    const retry = elements(render()).find(element => element.props.children === "Retry chat continuation")!;
    (retry.props.onClick as () => void)(); await settle();
    expect(h.send).toHaveBeenCalledTimes(2);
    expect(h.send.mock.calls[1]).toEqual(h.send.mock.calls[0]);
    expect(elements(render()).some(element => element.props.role === "alert")).toBe(false);
  });
  it("disables another thread but retains a captured REST receipt on its original thread", async () => {
    h.send.mockResolvedValue("error");
    const original = consent(); h.thread = "other";
    expect(consent().props.disabled).toBe(true);
    (original.props.onAccepted as (value: unknown) => void)({ caseId: "recorded" }); await settle();
    expect(h.send).toHaveBeenCalledWith("original", "proposal", { type: "dispute_preview_decision", payload: { caseId: "recorded", declined: false } });
    h.send.mockResolvedValue("error");
    const retry = elements(render()).find(element => element.props.children === "Retry chat continuation")!;
    expect(retry.props.disabled).toBe(true);
  });
  it("keeps a rerendered late decision bound to the original thread", async () => {
    h.send.mockResolvedValueOnce("error");
    consent(); h.thread = "other";
    (consent().props.onAccepted as (value: unknown) => void)({ caseId: "recorded" }); await settle();
    expect(h.send).toHaveBeenCalledWith("original", "proposal", { type: "dispute_preview_decision", payload: { caseId: "recorded", declined: false } });
    h.thread = "original";
    const retry = elements(render()).find(element => element.props.children === "Retry chat continuation")!;
    expect(retry.props.disabled).toBe(false);
    (retry.props.onClick as () => void)(); await settle();
    expect(h.send).toHaveBeenCalledWith("original", "proposal", { type: "dispute_preview_decision", payload: { caseId: "recorded", declined: false } });
  });
  it("disables consent and continuation retry for a locked thread", async () => {
    h.send.mockResolvedValueOnce("error");
    (consent().props.onAccepted as (value: unknown) => void)({ caseId: "recorded" }); await settle();
    h.locked = true;
    expect(consent().props.disabled).toBe(true);
    expect(elements(render()).find(element => element.props.children === "Retry chat continuation")?.props.disabled).toBe(true);
  });
  it("forwards only bounded visible messages to REST consent", () => {
    h.items = Array.from({ length: 110 }, (_, index) => ({ id: String(index), thread_id: "original", created_at: "today", type: "user_message", content: [{ type: "input_text", text: String(index) }], attachments: [] }));
    h.items.push({ id: "tool", thread_id: "original", created_at: "today", type: "client_widget", name: "tool_approval_request", args: { secret: "hidden" } });
    expect(consent().props.conversationHistory).toEqual(Array.from({ length: 100 }, (_, index) => ({ role: "user", text: String(index + 10) })));
  });
  it("disables consent during streaming", () => { h.streaming = true; expect(consent().props.disabled).toBe(true); });
});
