import { type ReactElement, type ReactNode, isValidElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/api/errors";
import SupportCases from "./SupportCases";

const h = vi.hoisted(() => ({
  cursor: 0, states: [] as unknown[], effects: [] as Array<() => void | (() => void)>,
  dependencies: [] as unknown[][], list: vi.fn(), poll: vi.fn(), logout: vi.fn(), sessionKey: "session-1",
}));
vi.mock("react", async original => ({
  ...await original<typeof import("react")>(),
  useState: (initial: unknown) => {
    const i = h.cursor++;
    if (!(i in h.states)) h.states[i] = initial;
    return [h.states[i], (value: unknown) => { h.states[i] = typeof value === "function" ? value(h.states[i]) : value; }];
  },
  useEffect: (effect: () => void | (() => void), dependencies: unknown[]) => {
    h.effects.push(effect); h.dependencies.push(dependencies);
  },
}));
vi.mock("react-router-dom", () => ({ Link: "a" }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: { id: "customer", identityVersion: 1, locale: "en" }, sessionKey: h.sessionKey, logout: h.logout }) }));
vi.mock("@/api/disputeClient", () => ({ listSupportCases: h.list }));
vi.mock("@/api/disputePolling", () => ({ startDisputePolling: h.poll }));

function elements(node: ReactNode): ReactElement<Record<string, unknown>>[] {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!isValidElement<Record<string, unknown>>(node)) return [];
  return [node, ...elements(node.props.children as ReactNode)];
}
function text(node: ReactNode): string {
  if (Array.isArray(node)) return node.map(text).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) return text(node.props.children);
  return typeof node === "string" || typeof node === "number" ? String(node) : "";
}
function render() { h.cursor = 0; h.effects = []; h.dependencies = []; return SupportCases(); }
function item(productNumber = "1234567890123456") {
  return { caseId: "case/" + "a".repeat(120), status: "IN_REVIEW", reason: "Original statement\n" + "x".repeat(200), openedAt: "2026-10-04T10:00:00Z", productNumber };
}
beforeEach(() => {
  vi.clearAllMocks(); h.states = []; h.effects = []; h.dependencies = []; h.sessionKey = "session-1";
});

describe("customer case list readiness", () => {
  it("masks full card numbers and safely encodes complete case links", () => {
    const record = item(); h.states = [[record], false, null, 0];
    const tree = render(); const nodes = elements(tree);
    expect(text(tree)).toContain("1234 **** **** 3456");
    expect(text(tree)).not.toContain(record.productNumber);
    expect(nodes.find(e => e.type === "a")?.props.to).toBe(`/support-cases/${encodeURIComponent(record.caseId)}`);
    expect(nodes.find(e => e.type === CardTitle)?.props.children).toBe(record.caseId);
    expect(nodes.find(e => e.type === CardTitle)?.props.className).toContain("[overflow-wrap:anywhere]");
    expect(nodes.find(e => e.type === CardHeader)?.props.className).toContain("flex-wrap");
    expect(nodes.find(e => e.type === "p" && e.props.children === record.reason)?.props.className).toContain("whitespace-pre-wrap");
    expect(nodes[0].props.className).toContain("sm:p-6");
  });

  it("uses an unavailable label instead of exposing an invalid card identifier", () => {
    h.states = [[item("unexpected-private-identifier")], false, null, 0];
    const output = text(render());
    expect(output).toContain("Unavailable");
    expect(output).not.toContain("unexpected-private-identifier");
  });

  it("shows loading and empty states and supports repeated refresh", () => {
    expect(text(render())).toContain("Loading support cases...");
    h.states[1] = false;
    const nodes = elements(render());
    expect(text(render())).toContain("No support cases yet.");
    const refresh = nodes.find(e => typeof e.props.onClick === "function")!.props.onClick as () => void;
    refresh(); refresh();
    expect(h.states[3]).toBe(2);
  });

  it.each([
    [new ApiError("AUTH_REQUIRED"), "Session expired", true],
    [new Error("private backend detail"), "Support cases are unavailable", false],
  ])("controls failed polls and only logs out for authentication failures", async (cause, expected, logout) => {
    h.list.mockRejectedValue(cause); render(); h.effects[1]();
    const request = h.poll.mock.calls[0][0] as (signal: AbortSignal) => Promise<void>;
    await request(new AbortController().signal);
    expect(h.states[2]).toBe(expected);
    expect(h.states[1]).toBe(false);
    expect(h.logout).toHaveBeenCalledTimes(logout ? 1 : 0);
    const nodes = elements(render());
    expect(nodes.find(e => e.props.role === "alert")?.props.children).toBe(expected);
    expect(text(render())).not.toContain("private backend detail");
  });

  it.each(["success", "failure"])("ignores late %s after polling cleanup and resets the session list", async outcome => {
    let finish!: (value: unknown) => void; let fail!: (reason: unknown) => void;
    h.list.mockReturnValue(new Promise((resolve, reject) => { finish = resolve; fail = reject; }));
    const controller = new AbortController(); h.poll.mockReturnValue(() => controller.abort());
    h.states = [[item()], false, null, 0]; render();
    const cleanup = h.effects[1]() as () => void;
    const request = h.poll.mock.calls[0][0] as (signal: AbortSignal) => Promise<void>;
    const pending = request(controller.signal);
    cleanup(); h.sessionKey = "session-2"; render(); h.effects[0]();
    expect(h.dependencies[1]).toContain("session-2");
    if (outcome === "success") finish([item()]); else fail(new ApiError("AUTH_REQUIRED"));
    await pending;
    expect(h.states[0]).toEqual([]);
    expect(h.states[1]).toBe(true);
    expect(h.states[2]).toBeNull();
    expect(h.logout).not.toHaveBeenCalled();
  });
});
