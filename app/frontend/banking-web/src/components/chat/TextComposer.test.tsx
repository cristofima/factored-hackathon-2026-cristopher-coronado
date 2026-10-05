import { isValidElement, type ReactElement, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Composer } from "./TextComposer";
import { Textarea } from "@/components/ui/textarea";

const h = vi.hoisted(() => ({ value: "Question", locked: false, help: false, streaming: false, closed: false, send: vi.fn(), close: vi.fn(), continue: vi.fn() }));
vi.mock("react", async original => ({ ...await original<typeof import("react")>(), useState: () => [h.value, (value: string) => { h.value = value; }], useMemo: (factory: () => unknown) => factory() }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("./ResponsesChatProvider", () => ({ useChat: () => ({ sendMessage: h.send, cancelStreaming: vi.fn(), isStreaming: h.streaming, activeThreadId: "thread", activeThread: { metadata: { furtherHelp: h.help }, status: { type: h.closed ? "closed" : "locked" } }, isThreadLocked: () => h.locked, closeThread: h.close, setFurtherHelp: h.continue }) }));
type Element = ReactElement<Record<string, unknown>>;
function elements(node: ReactNode): Element[] {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!isValidElement<Record<string, unknown>>(node)) return [];
  return [node, ...elements(node.props.children as ReactNode)];
}
beforeEach(() => { vi.clearAllMocks(); h.value = "Question"; h.locked = false; h.help = false; h.streaming = false; h.closed = false; });
describe("chat composer thread controls", () => {
  it("offers explicit continue and close actions after acceptance", () => {
    h.help = true;
    const controls = elements(Composer({}));
    expect(controls.find(element => element.props.role === "group")?.props["aria-label"]).toBe("Can I help with anything else?");
    expect(controls.find(element => element.props.children === "Continue chatting")!.props.variant).toBe("default");
    expect(controls.find(element => element.props.children === "Close conversation")!.props.variant).toBe("destructive");
    expect(controls.some(element => String(element.props.className).includes("sm:gap-6"))).toBe(true);
    (controls.find(element => element.props.children === "Continue chatting")!.props.onClick as () => void)();
    (controls.find(element => element.props.children === "Close conversation")!.props.onClick as () => void)();
    expect(h.continue).toHaveBeenCalledWith("thread", false);
    expect(h.close).toHaveBeenCalledWith("thread");
  });
  it.each(["closed", "recovered", "help", "streaming", "empty"])("guards Enter submission for %s", mode => {
    h.locked = mode === "closed" || mode === "recovered"; h.closed = mode === "closed";
    h.help = mode === "help"; h.streaming = mode === "streaming"; if (mode === "empty") h.value = "  ";
    const controls = elements(Composer({}));
    const textarea = controls.find(element => element.type === Textarea)!;
    (textarea.props.onKeyDown as (event: unknown) => void)({ key: "Enter", shiftKey: false, preventDefault: vi.fn() });
    expect(h.send).not.toHaveBeenCalled();
    if (h.locked) expect(controls.find(element => element.props.role === "status")?.props.children).toBe(h.closed ? "Conversation closed" : "Recovered conversation is read-only. Start a new conversation to continue.");
  });
  it("hides both explicit help controls while acknowledgment streams", () => {
    h.help = true; h.streaming = true;
    const controls = elements(Composer({}));
    for (const label of ["Continue chatting", "Close conversation"]) {
      expect(controls.find(element => element.props.children === label)).toBeUndefined();
    }
  });
  it("sends ordinary text without language-based closure", () => {
    h.value = "no";
    const textarea = elements(Composer({})).find(element => element.type === Textarea)!;
    (textarea.props.onKeyDown as (event: unknown) => void)({ key: "Enter", shiftKey: false, preventDefault: vi.fn() });
    expect(h.send).toHaveBeenCalledWith("no"); expect(h.close).not.toHaveBeenCalled();
  });
});
