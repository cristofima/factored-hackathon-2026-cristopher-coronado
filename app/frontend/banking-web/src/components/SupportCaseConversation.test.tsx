import { type ReactElement, type ReactNode, isValidElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/errors";
import SupportCaseConversation from "./SupportCaseConversation";
import { Markdown } from "@/components/chat/Markdown";
import { Accordion, AccordionContent } from "@/components/ui/accordion";

const h = vi.hoisted(() => ({
  effects: [] as Array<() => void>,
  user: { id: "customer-1", identityVersion: 2 } as { id: string; identityVersion: number } | null,
  sessionKey: "session-1", logout: vi.fn(), queryOptions: vi.fn(),
  history: { data: undefined as { source: string; messages: Array<{ role: string; text: string }> } | undefined, isPending: false, error: null as unknown, refetch: vi.fn() },
  customerGetter: vi.fn(), operatorGetter: vi.fn(),
}));
vi.mock("react", async original => ({
  ...await original<typeof import("react")>(),
  useEffect: (effect: () => void) => { h.effects.push(effect); },
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@tanstack/react-query", () => ({ useQuery: (options: unknown) => { h.queryOptions(options); return h.history; } }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: h.user, sessionKey: h.sessionKey, logout: h.logout }) }));
vi.mock("@/api/disputeClient", () => ({ getCaseConversation: h.customerGetter }));
vi.mock("@/api/operatorDisputeClient", () => ({ getOperatorCaseConversation: h.operatorGetter }));

type Element = ReactElement<Record<string, unknown>>;
function elements(node: ReactNode): Element[] {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!isValidElement<Record<string, unknown>>(node)) return [];
  return [node, ...elements(node.props.children as ReactNode)];
}
function text(node: ReactNode): string {
  if (Array.isArray(node)) return node.map(text).join("");
  if (isValidElement<Record<string, unknown>>(node)) return text(node.props.children as ReactNode);
  return typeof node === "string" || typeof node === "number" ? String(node) : "";
}
function render(caseId = "case-1", operator = false): ReactNode {
  h.effects = [];
  return SupportCaseConversation({ caseId, operator });
}
beforeEach(() => {
  vi.clearAllMocks(); h.effects = []; h.user = { id: "customer-1", identityVersion: 2 }; h.sessionKey = "session-1";
  h.history = { data: undefined, isPending: false, error: null, refetch: vi.fn() };
});

describe("support-case conversation viewer", () => {
  it("uses the shared chat Markdown renderer without altering ordered evidence or executing HTML", () => {
    const messages = [
      { role: "user", text: "Original reason\n\n**bold**\n\n<script>alert('literal')</script>" },
      { role: "assistant", text: "<strong>not HTML</strong> [link](https://example.test)\n\n| Merchant | Status |\n| --- | --- |\n| Store | Approved |" },
    ];
    h.history.data = { source: "CUSTOMER_PROVIDED", messages };
    const tree = render();
    expect(text(tree)).toContain("Case conversation provenance");
    const items = elements(tree).filter(element => element.type === "li");
    expect(items).toHaveLength(2);
    expect(items.map(item => elements(item).filter(element => element.type === "p").map(text))).toEqual([
      ["Customer"], ["Assistant"],
    ]);
    const bodies = elements(tree).filter(element => element.type === Markdown);
    expect(bodies.map(body => body.props.content)).toEqual(messages.map(message => message.text));
    const html = bodies.map(body => renderToStaticMarkup(body)).join("");
    expect(html).toContain("<strong>bold</strong>");
    expect(html).toContain("<table>");
    expect(html).toContain('target="_blank" rel="noopener noreferrer"');
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("&lt;strong&gt;not HTML&lt;/strong&gt;");
    expect(html).not.toContain("<script");
  });
  it.each([false, true])("starts collapsed with accessible expand/collapse controls (operator=%s)", operator => {
    h.history.data = { source: "CUSTOMER_PROVIDED", messages: [{ role: "user", text: "Saved conversation" }] };
    const tree = render("case-1", operator);
    const accordion = elements(tree).find(element => element.type === Accordion)!;
    expect(accordion.props).toMatchObject({ type: "single", collapsible: true });
    expect(accordion.props).not.toHaveProperty("defaultValue");
    const collapsed = renderToStaticMarkup(tree);
    expect(collapsed).toContain('aria-expanded="false"');
    expect(collapsed).not.toContain("Saved conversation");
    const content = elements(tree).find(element => element.type === AccordionContent)!;
    const expanded = renderToStaticMarkup(<Accordion type="single" collapsible defaultValue="conversation">{accordion.props.children as ReactNode}</Accordion>);
    expect(expanded).toContain('aria-expanded="true"');
    expect(text(content)).toContain("Case conversation provenance");
    expect(expanded).toContain("Saved conversation");
  });
  it("shows accessible loading without claiming an empty history", () => {
    h.history.isPending = true;
    const tree = render();
    expect(text(elements(tree).find(element => element.props.role === "status"))).toBe("Loading conversation...");
    expect(text(tree)).not.toContain("No conversation saved");
    expect(text(tree)).not.toContain("Conversation unavailable");
  });
  it("shows an explicit empty history", () => {
    h.history.data = { source: "CUSTOMER_PROVIDED", messages: [] };
    const tree = render();
    expect(text(tree)).toContain("No conversation saved");
    expect(elements(tree).filter(element => element.type === "li")).toHaveLength(0);
    expect(text(tree)).not.toContain("Loading conversation...");
  });
  it("shows only a controlled error and retries the same query", () => {
    h.history.error = new Error("private backend detail");
    const tree = render();
    const alert = elements(tree).find(element => element.props.role === "alert");
    expect(text(alert)).toBe("Conversation unavailableRetry");
    expect(text(tree)).not.toContain("private backend detail");
    const retry = elements(tree).find(element => typeof element.props.onClick === "function" && text(element) === "Retry")!;
    (retry.props.onClick as () => void)();
    expect(h.history.refetch).toHaveBeenCalledOnce();
    h.effects.forEach(effect => effect());
    expect(h.logout).not.toHaveBeenCalled();
  });
  it.each(["AUTH_REQUIRED", "ACCESS_DENIED", "CASE_NOT_FOUND", "SERVICE_UNAVAILABLE"] as const)("logs out only for expired auth, not %s failures", code => {
    h.history.error = new ApiError(code);
    render(); h.effects.forEach(effect => effect());
    expect(h.logout).toHaveBeenCalledTimes(code === "AUTH_REQUIRED" ? 1 : 0);
  });
  it("hides history and disables reads when no authenticated identity exists", () => {
    h.user = null;
    h.history.data = { source: "CUSTOMER_PROVIDED", messages: [{ role: "user", text: "previous identity" }] };
    expect(render()).toBeNull();
    expect(h.queryOptions.mock.calls[0][0]).toMatchObject({ enabled: false });
    expect(h.customerGetter).not.toHaveBeenCalled();
    expect(h.operatorGetter).not.toHaveBeenCalled();
  });
  it("partitions queries by case, audience, session, user and identity version", () => {
    render(); render("case-2"); render("case-2", true);
    h.sessionKey = "session-2"; render("case-2", true);
    h.user = { id: "operator-2", identityVersion: 2 }; render("case-2", true);
    h.user.identityVersion = 3; render("case-2", true);
    expect(h.queryOptions.mock.calls.map(([options]) => options.queryKey)).toEqual([
      ["case-conversation", false, "case-1", "session-1", "customer-1", 2],
      ["case-conversation", false, "case-2", "session-1", "customer-1", 2],
      ["case-conversation", true, "case-2", "session-1", "customer-1", 2],
      ["case-conversation", true, "case-2", "session-2", "customer-1", 2],
      ["case-conversation", true, "case-2", "session-2", "operator-2", 2],
      ["case-conversation", true, "case-2", "session-2", "operator-2", 3],
    ]);
    for (const [options] of h.queryOptions.mock.calls) expect(options).toMatchObject({ enabled: true, retry: false, gcTime: 0 });
  });
  it.each([false, true])("selects the correct getter and forwards query cancellation (operator=%s)", async operator => {
    const data = { source: "CUSTOMER_PROVIDED", messages: [] };
    const getter = operator ? h.operatorGetter : h.customerGetter;
    const other = operator ? h.customerGetter : h.operatorGetter;
    getter.mockResolvedValue(data);
    render("case /1", operator);
    const controller = new AbortController();
    expect(await h.queryOptions.mock.calls[0][0].queryFn({ signal: controller.signal })).toBe(data);
    expect(getter).toHaveBeenCalledExactlyOnceWith("case /1", controller.signal);
    expect(other).not.toHaveBeenCalled();
  });
});
