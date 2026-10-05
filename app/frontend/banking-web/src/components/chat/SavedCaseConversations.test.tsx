import { type ReactElement, type ReactNode, isValidElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/errors";
import SupportCaseConversation from "@/components/SupportCaseConversation";
import { SavedCaseConversations } from "./SavedCaseConversations";

const h = vi.hoisted(() => ({
  user: { id: "customer-1", identityVersion: 1, role: "customer" } as { id: string; identityVersion: number; role: string } | null,
  sessionKey: 1, selection: null as { scope: string; caseId: string } | null,
  effects: [] as Array<() => void>, options: vi.fn(), logout: vi.fn(), list: vi.fn(),
  result: { data: undefined as Array<{ caseId: string; status: string }> | undefined, isPending: false, error: null as unknown, refetch: vi.fn() },
}));
vi.mock("react", async original => ({ ...await original<typeof import("react")>(),
  useState: () => [h.selection, (value: typeof h.selection) => { h.selection = value; }],
  useEffect: (effect: () => void) => { h.effects.push(effect); },
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@tanstack/react-query", () => ({ useQuery: (options: unknown) => { h.options(options); return h.result; } }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: h.user, sessionKey: h.sessionKey, logout: h.logout }) }));
vi.mock("@/api/disputeClient", () => ({ listSupportCases: h.list }));
type Element = ReactElement<Record<string, unknown>>;
function elements(node: ReactNode): Element[] {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!isValidElement<Record<string, unknown>>(node)) return [];
  return [node, ...elements(node.props.children as ReactNode)];
}
function text(node: ReactNode): string {
  if (Array.isArray(node)) return node.map(text).join("");
  if (isValidElement<Record<string, unknown>>(node)) return text(node.props.children as ReactNode);
  return typeof node === "string" ? node : "";
}
beforeEach(() => {
  vi.clearAllMocks(); h.effects = []; h.selection = null; h.sessionKey = 1;
  h.user = { id: "customer-1", identityVersion: 1, role: "customer" };
  h.result = { data: undefined, isPending: false, error: null, refetch: vi.fn() };
});
describe("saved case conversations in Help", () => {
  it("loads only authenticated customer cases using the abort signal", () => {
    SavedCaseConversations();
    const options = h.options.mock.calls[0][0];
    expect(options).toMatchObject({ enabled: true, retry: false, gcTime: 0, queryKey: ["help-case-conversations", "customer-1", 1, 1] });
    const signal = new AbortController().signal;
    options.queryFn({ signal }); expect(h.list).toHaveBeenCalledWith(signal);
  });
  it.each([null, { id: "staff", identityVersion: 1, role: "operator" }])("hides customer evidence and disables reads for %s", user => {
    h.user = user;
    expect(SavedCaseConversations()).toBeNull();
    expect(h.options.mock.calls[0][0].enabled).toBe(false);
    expect(h.list).not.toHaveBeenCalled();
  });
  it("mounts only selected read-only evidence, never a chat continuation", () => {
    h.result.data = [{ caseId: "case/1", status: "IN_REVIEW" }, { caseId: "case-2", status: "RESOLVED_VALID" }];
    let tree = SavedCaseConversations();
    expect(elements(tree).filter(e => e.type === SupportCaseConversation)).toHaveLength(0);
    const button = elements(tree).find(e => e.props["aria-pressed"] === false)!;
    (button.props.onClick as () => void)(); tree = SavedCaseConversations();
    expect(elements(tree).filter(e => e.type === SupportCaseConversation).map(e => e.props)).toEqual([{ caseId: "case/1" }]);
    expect(elements(tree).find(e => e.props.to)?.props.to).toBe("/support-cases/case%2F1");
    expect(text(tree)).toContain("Saved case conversations description");
    expect(elements(tree).some(e => e.type === "textarea" || e.type === "form")).toBe(false);
    h.sessionKey = 2;
    expect(elements(SavedCaseConversations()).some(e => e.type === SupportCaseConversation)).toBe(false);
    h.user = { id: "customer-2", identityVersion: 1, role: "customer" };
    expect(elements(SavedCaseConversations()).some(e => e.type === SupportCaseConversation)).toBe(false);
  });
  it.each(["version", "removed", "error"])("hides stale selected evidence after %s changes", change => {
    h.result.data = [{ caseId: "case-1", status: "IN_REVIEW" }];
    h.selection = { scope: JSON.stringify(["customer-1", 1, 1]), caseId: "case-1" };
    expect(elements(SavedCaseConversations()).some(e => e.type === SupportCaseConversation)).toBe(true);
    if (change === "version") h.user!.identityVersion = 2;
    if (change === "removed") h.result.data = [];
    if (change === "error") h.result.error = new ApiError("ACCESS_DENIED");
    expect(elements(SavedCaseConversations()).some(e => e.type === SupportCaseConversation)).toBe(false);
  });
  it("distinguishes loading and empty results", () => {
    h.result.isPending = true;
    expect(elements(SavedCaseConversations()).some(e => e.props.role === "status")).toBe(true);
    expect(text(SavedCaseConversations())).not.toContain("No support cases yet.");
    h.result.isPending = false; h.result.data = [];
    expect(text(SavedCaseConversations())).toContain("No support cases yet.");
  });
  it.each(["ACCESS_DENIED", "AUTH_REQUIRED", "SERVICE_UNAVAILABLE"] as const)("shows controlled %s error, retries, and expires only auth", code => {
    h.result.error = new ApiError(code);
    const tree = SavedCaseConversations();
    expect(text(tree)).toContain("Conversation unavailable");
    expect(text(tree)).not.toContain("private detail");
    const retry = elements(tree).find(e => typeof e.props.onClick === "function" && text(e) === "Retry")!;
    (retry.props.onClick as () => void)(); expect(h.result.refetch).toHaveBeenCalledOnce();
    h.effects.forEach(effect => effect());
    expect(h.logout).toHaveBeenCalledTimes(code === "AUTH_REQUIRED" ? 1 : 0);
  });
});
