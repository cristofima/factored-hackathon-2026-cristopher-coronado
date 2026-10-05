import { type ReactElement, type ReactNode, isValidElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CardHeader } from "@/components/ui/card";
import SupportCaseConversation from "@/components/SupportCaseConversation";
import SupportCaseTimeline from "@/components/SupportCaseTimeline";
import SupportCaseDetail from "./SupportCaseDetail";
import { ApiError } from "@/api/errors";
import { createInstance } from "i18next";
import en from "@/locales/en.json";
import es from "@/locales/es.json";
import pt from "@/locales/pt.json";

const h = vi.hoisted(() => ({
  cursor: 0, states: [] as unknown[], refs: [] as Array<{ current: unknown }>, refCursor: 0,
  effects: [] as Array<() => void | (() => void)>, caseId: "case-" + "a".repeat(128),
  logout: vi.fn(), poll: vi.fn(), respond: vi.fn(), dismiss: vi.fn(), sessionKey: "session-1",
  translate: (key: string) => key,
}));
vi.mock("react", async original => ({
  ...await original<typeof import("react")>(),
  useState: (initial: unknown) => {
    const i = h.cursor++;
    if (!(i in h.states)) h.states[i] = initial;
    return [h.states[i], (value: unknown) => { h.states[i] = typeof value === "function" ? value(h.states[i]) : value; }];
  },
  useEffect: (effect: () => void | (() => void)) => { h.effects.push(effect); },
  useRef: (initial: unknown) => { const i = h.refCursor++; return h.refs[i] ?? (h.refs[i] = { current: initial }); },
}));
vi.mock("react-router-dom", () => ({ useParams: () => ({ caseId: h.caseId }), Link: "a" }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => h.translate(key) }) }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: { id: "customer", identityVersion: 1 }, sessionKey: h.sessionKey, logout: h.logout }) }));
vi.mock("@/api/disputePolling", () => ({ startDisputePolling: h.poll }));
vi.mock("@/api/disputeClient", () => ({ respondToSupportCaseApproval: h.respond, dismissSupportCaseRecommendation: h.dismiss, getSupportCaseDetail: vi.fn() }));

function elements(node: ReactNode): ReactElement<Record<string, unknown>>[] {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!isValidElement<Record<string, unknown>>(node)) return [];
  return [node, ...elements(node.props.children as ReactNode)];
}
function render() { h.cursor = 0; h.refCursor = 0; h.effects = []; return SupportCaseDetail(); }
function control(label: string) {
  return elements(render()).find(e => typeof e.props.onClick === "function" && e.props.children === label)!;
}
beforeEach(() => {
  vi.resetAllMocks(); h.cursor = 0; h.refCursor = 0; h.states = []; h.refs = []; h.effects = []; h.sessionKey = "session-1";
  h.translate = (key: string) => key;
});

describe("customer case detail layout", () => {
  it("places conversation history below the timeline", () => {
    h.states[0] = { caseId: h.caseId, status: "IN_REVIEW", transactionId: "tx", reason: "Original statement" };
    const output = elements(render());
    const timeline = output.findIndex(e => e.type === SupportCaseTimeline);
    const conversation = output.findIndex(e => e.type === SupportCaseConversation);
    expect(timeline).toBeGreaterThan(-1);
    expect(conversation).toBeGreaterThan(timeline);
  });
  it("keeps the complete case reference wrappable and stacks refresh on narrow screens", () => {
    const output = elements(render());
    const heading = output.find(e => e.type === "h1")!;
    expect(heading.props.children).toBe(h.caseId);
    expect(heading.props.className).toContain("[overflow-wrap:anywhere]");
    const header = output.find(e => e.type === "div" && Array.isArray(e.props.children) && e.props.children.includes(heading))!;
    expect(output[0].props.className).toContain("min-w-0");
    expect(header.props.className).toContain("flex-col");
    expect(header.props.className).toContain("sm:flex-row");
  });
  it("allows localized status and legacy consent actions to wrap without changing controls", () => {
    h.states[0] = { caseId: h.caseId, status: "WAITING_USER_APPROVAL", transactionId: "tx", reason: "Original statement" };
    const output = elements(render());
    expect(output.find(e => e.type === CardHeader)?.props.className).toContain("flex-wrap");
    const actions = output.find(e => e.type === "div" && e.props.className === "flex flex-wrap gap-3")!;
    expect(elements(actions).filter(e => typeof e.props.onClick === "function").map(e => e.props.children)).toEqual(["Approve dispute", "Decline"]);
  });
});

describe("customer unavailable case navigation", () => {
  it.each([
    ["en", en, "Transaction Disputes"],
    ["es", es, "Reclamos de transacciones"],
    ["pt", pt, "Contestações de transações"],
  ] as const)("localizes the unavailable page in %s", async (locale, catalog, title) => {
    const i18n = createInstance();
    await i18n.init({ lng: locale, fallbackLng: false, keySeparator: false, resources: { [locale]: { translation: catalog } } });
    h.translate = (key: string) => i18n.t(key);
    h.states[3] = "Case not available";
    const output = elements(render());
    expect(output.find(e => e.type === "h1")?.props.children).toBe(title);
    expect(output.find(e => e.props.role === "alert")?.props.children).toBe(catalog["Case not available"]);
    expect(output.find(e => e.props.to === "/support-cases")?.props.children).toBe(catalog["Back to support cases"]);
  });
  it.each(["CASE_NOT_FOUND", "ACCESS_DENIED", "DISPUTE_UNAVAILABLE"] as const)("presents %s identically without previous case data", async code => {
    render(); h.effects[0]();
    h.states[0] = { caseId: h.caseId, reason: "Previous private statement" };
    h.states[1] = [{ message: "Previous event" }];
    const { getSupportCaseDetail } = await import("@/api/disputeClient");
    vi.mocked(getSupportCaseDetail).mockRejectedValueOnce(new ApiError(code));
    h.effects[1]();
    await h.poll.mock.calls[0][0](new AbortController().signal);
    expect(h.states[0]).toBeNull(); expect(h.states[1]).toEqual([]);
    const output = elements(render());
    expect(output.find(e => e.props.role === "alert")?.props.children).toBe("Case not available");
    expect(output.find(e => e.props.to === "/support-cases")?.props.children).toBe("Back to support cases");
    expect(h.logout).not.toHaveBeenCalled();
  });
  it("preserves refresh for transient failures", () => {
    h.states[3] = "Support case is unavailable";
    const refresh = elements(render()).find(e => typeof e.props.onClick === "function" && Array.isArray(e.props.children) && e.props.children.includes("Refresh"));
    expect(refresh).toBeDefined();
    (refresh!.props.onClick as () => void)();
    expect(h.states[6]).toBe(1);
    expect(elements(render()).some(e => e.props.to === "/support-cases")).toBe(false);
  });
});

describe("customer case action isolation", () => {
  it("suppresses duplicate approval clicks and applies the server readback", async () => {
    h.states[0] = { caseId: h.caseId, status: "WAITING_USER_APPROVAL" };
    let finish!: (value: unknown) => void;
    h.respond.mockReturnValue(new Promise(resolve => { finish = resolve; }));
    const stop = vi.fn(); h.poll.mockReturnValue(stop);
    const approve = control("Approve dispute").props.onClick as () => Promise<void>;
    h.effects[1]();
    const pending = approve();
    expect(stop).toHaveBeenCalledOnce();
    await approve();
    expect(h.respond).toHaveBeenCalledTimes(1);
    expect(h.states[5]).toBe(true);
    const updated = { caseId: h.caseId, status: "IN_REVIEW" };
    finish(updated); await pending;
    expect(h.states[0]).toBe(updated);
    expect(h.states[5]).toBe(false);
    expect(elements(render()).some(e => e.props.children === "Approve dispute")).toBe(false);
  });

  it("aborts approval and ignores its late readback after identity cleanup", async () => {
    render();
    const cleanup = h.effects[0]() as () => void;
    h.states[0] = { caseId: h.caseId, status: "WAITING_USER_APPROVAL" };
    let finish!: (value: unknown) => void;
    h.respond.mockReturnValue(new Promise(resolve => { finish = resolve; }));
    const pending = (control("Approve dispute").props.onClick as () => Promise<void>)();
    const signal = h.respond.mock.calls[0][2] as AbortSignal;
    cleanup(); h.sessionKey = "session-2"; render(); h.effects[0]();
    finish({ caseId: h.caseId, status: "IN_REVIEW" }); await pending;
    expect(signal.aborted).toBe(true);
    expect(h.states[0]).toBeNull();
    expect(h.states[5]).toBe(false);
    expect(h.logout).not.toHaveBeenCalled();
  });

  it("records one recommendation dismissal and hides it only after server readback", async () => {
    h.states[0] = { caseId: h.caseId, status: "RESOLVED_VALID", recommendationType: "CARD_SECURITY", recommendationOptedOut: false };
    let finish!: (value: unknown) => void;
    h.dismiss.mockReturnValue(new Promise(resolve => { finish = resolve; }));
    const dismiss = control("Dismiss recommendation").props.onClick as () => Promise<void>;
    const pending = dismiss(); await dismiss();
    expect(h.dismiss).toHaveBeenCalledTimes(1);
    expect(control("Dismiss recommendation").props.disabled).toBe(true);
    finish({ caseId: h.caseId, status: "RESOLVED_VALID", recommendationType: "CARD_SECURITY", recommendationOptedOut: true });
    await pending;
    expect(elements(render()).some(e => e.props.children === "Dismiss recommendation")).toBe(false);
  });

  it("keeps legacy consent available on unknown action errors with a controlled message", async () => {
    h.states[0] = { caseId: h.caseId, status: "WAITING_USER_APPROVAL" };
    h.respond.mockRejectedValue(new Error("private backend detail"));
    await (control("Approve dispute").props.onClick as () => Promise<void>)();
    expect(h.states[4]).toBe("Could not record your response");
    expect(control("Approve dispute").props.disabled).toBe(false);
    expect(h.logout).not.toHaveBeenCalled();
  });

  it("logs out on current-session authentication failure without exposing server messages", async () => {
    h.states[0] = { caseId: h.caseId, status: "WAITING_USER_APPROVAL" };
    h.respond.mockRejectedValue(new ApiError("AUTH_REQUIRED"));
    await (control("Decline").props.onClick as () => Promise<void>)();
    expect(h.logout).toHaveBeenCalledOnce();
    expect(h.states[4]).toBe("Session expired");
    expect(h.states[5]).toBe(false);
  });
});
