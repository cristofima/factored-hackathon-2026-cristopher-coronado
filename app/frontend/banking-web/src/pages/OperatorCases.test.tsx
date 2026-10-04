import { type ReactElement, type ReactNode, isValidElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/errors";
import { Badge } from "@/components/ui/badge";
import { CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import OperatorCases from "./OperatorCases";

const h = vi.hoisted(() => ({
  states: [] as unknown[], cursor: 0, refs: [] as Array<{ current: unknown }>, refCursor: 0,
  effects: [] as Array<() => void | (() => void)>, caseId: undefined as string | undefined,
  queue: { data: undefined as unknown, isPending: false, error: null as unknown, refetch: vi.fn() },
  detail: { data: undefined as unknown, isPending: false, error: null as unknown, refetch: vi.fn() },
  navigate: vi.fn(), queryOptions: vi.fn(), claim: vi.fn(), invalidate: vi.fn(), logout: vi.fn(), sessionKey: "session-1",
}));
vi.mock("react", async (original) => ({
  ...await original<typeof import("react")>(),
  useState: (initial: unknown) => { const i = h.cursor++; if (!(i in h.states)) h.states[i] = initial; return [h.states[i], (value: unknown) => { h.states[i] = value; }]; },
  useRef: (initial: unknown) => { const i = h.refCursor++; return h.refs[i] ?? (h.refs[i] = { current: initial }); },
  useEffect: (effect: () => void | (() => void)) => { h.effects.push(effect); },
}));
vi.mock("react-router-dom", () => ({ useParams: () => ({ caseId: h.caseId }), Link: "a", useNavigate: () => h.navigate }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@tanstack/react-query", () => ({
  useQuery: (options: { queryKey: unknown[] }) => { h.queryOptions(options); return options.queryKey.at(-2) === "queue" ? h.queue : h.detail; },
  useQueryClient: () => ({ invalidateQueries: h.invalidate }),
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: { id: "operator-id", identityVersion: 3, locale: "en" }, sessionKey: h.sessionKey, logout: h.logout }) }));
vi.mock("@/api/operatorDisputeClient", () => ({ claimOperatorCase: h.claim, listOperatorCases: vi.fn(), getOperatorCase: vi.fn() }));

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
function render(): Element { h.cursor = 0; h.refCursor = 0; h.effects = []; return OperatorCases(); }
function button(label: string): Element {
  const control = elements(render()).find((e) => typeof e.props.onClick === "function" && text(e) === label);
  if (!control) throw new Error("Missing control " + label);
  return control;
}
const caseRecord = { caseId: "case-id", status: "IN_REVIEW", triageOutcome: null, openedAt: "2026-10-04T12:00:00Z", updatedAt: "2026-10-04T12:00:00Z", claimVersion: 0 };
const ownedCase = { ...caseRecord, claimVersion: 1, assignedOperatorSub: "operator-id", claimedAt: caseRecord.openedAt, reason: "Customer-entered reason", transactionId: "tx-id", productId: "product-id", events: [] };
const settle = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
beforeEach(() => {
  vi.clearAllMocks(); h.states = []; h.refs = []; h.effects = []; h.caseId = undefined; h.sessionKey = "session-1";
  h.queue = { data: { items: [caseRecord], total: 1, offset: 0, limit: 50 }, isPending: false, error: null, refetch: vi.fn() };
  h.detail = { data: undefined, isPending: false, error: null, refetch: vi.fn() };
  h.claim.mockResolvedValue(ownedCase); h.invalidate.mockResolvedValue(undefined);
});

describe("operator review queue", () => {
  it("groups queue identity and status separately from paired metadata and actions", () => {
    const output = elements(render());
    const header = output.find(e => e.type === CardHeader)!;
    expect(elements(header).some(e => e.type === CardTitle && text(e) === caseRecord.caseId)).toBe(true);
    expect(elements(header).some(e => e.type === Badge && text(e) === "support-cases.status.IN_REVIEW")).toBe(true);
    const metadata = output.find(e => e.type === "dl")!;
    expect(elements(metadata).filter(e => e.type === "dt" || e.type === "dd").map(text)).toEqual([
      "Opened", expect.any(String), "Claim version", "0",
    ]);
    expect(metadata.props.className).toContain("sm:grid-cols-");
    const footer = output.find(e => e.type === CardFooter)!;
    expect(text(footer)).toBe("Take case");
    expect(text(output.find(e => e.type === CardContent)!)).not.toContain("Take case");
  });
  it("separates the full-width unchanged reason from responsive assignment metadata", () => {
    const reason = "Customer reason\nSecond line with <literal> text";
    h.caseId = ownedCase.caseId;
    h.detail.data = { ...ownedCase, reason };
    const output = elements(render());
    const groups = output.filter(e => e.type === "dl");
    expect(groups).toHaveLength(2);
    expect(elements(groups[0]).filter(e => e.type === "dt" || e.type === "dd").map(text)).toEqual(["Reason", reason]);
    expect(groups[0].props.className).toContain("border");
    const reasonValue = elements(groups[0]).find(e => e.type === "dd")!;
    expect(reasonValue.props.className).toContain("whitespace-pre-wrap");
    expect(reasonValue.props.className).toContain("mt-2");
    expect(elements(groups[1]).filter(e => e.type === "dt" || e.type === "dd").map(text)).toEqual([
      "Claimed at", expect.any(String), "Claim version", "1",
    ]);
    expect(groups[1].props.className).toContain("grid-cols-1");
    expect(groups[1].props.className).toContain("sm:grid-cols-");
    expect(groups[1].props.className).toContain("border-t");
    const header = output.find(e => e.type === CardHeader)!;
    expect(text(header)).toContain("Assigned to you");
    expect(elements(header).some(e => e.type === Badge && text(e) === "support-cases.status.IN_REVIEW")).toBe(true);
    expect(text(header)).not.toContain(reason);
  });
  it("renders loading, empty and controlled retry states", () => {
    h.queue.isPending = true; expect(text(render())).toContain("Loading review queue...");
    h.queue.isPending = false; h.queue.data = { items: [], total: 0, offset: 0, limit: 50 }; expect(text(render())).toContain("No cases awaiting review");
    h.queue.error = new ApiError("SERVICE_UNAVAILABLE");
    expect(elements(render()).some((e) => e.props.role === "alert")).toBe(true);
    (button("Retry").props.onClick as () => void)(); expect(h.queue.refetch).toHaveBeenCalledOnce();
  });
  it.each([{ status: "RESOLVED" }, { status: "WAITING_USER_APPROVAL" }])("does not claim ineligible cases", (fields) => {
    h.queue.data = { items: [{ ...caseRecord, ...fields }], total: 1, offset: 0, limit: 50 };
    const control = button("Take case"); expect(control.props.disabled).toBe(true);
    (control.props.onClick as () => void)(); expect(h.claim).not.toHaveBeenCalled();
  });
  it("blocks duplicate clicks, reconciles the scoped cache and reports success", async () => {
    let resolve!: (value: typeof ownedCase) => void; h.claim.mockImplementation(() => new Promise<typeof ownedCase>((done) => { resolve = done; }));
    const click = button("Take case").props.onClick as () => void;
    click(); click(); expect(h.claim).toHaveBeenCalledOnce();
    expect(button("Taking case...").props.disabled).toBe(true);
    resolve(ownedCase); await settle();
    expect(h.invalidate).toHaveBeenCalledWith({ queryKey: ["operator-cases", "session-1", "operator-id", 3] });
    expect(h.navigate).toHaveBeenCalledWith("/operator/support-cases/case-id");
    h.states = []; h.refs = []; h.caseId = "case-id"; h.detail.data = ownedCase;
    expect(text(render())).toContain("Customer-entered reason");
    expect(text(render())).toContain("Assigned to you");
    expect(elements(render()).some(e => e.type === "dt" && text(e) === "Reason")).toBe(true);
    expect(elements(render()).some(e => e.type === "dd" && text(e) === ownedCase.reason)).toBe(true);
    expect(elements(render()).some(e => e.props.perspective === "operator" && e.props.events === ownedCase.events)).toBe(true);
    expect(ownedCase.reason).toBe("Customer-entered reason");
  });
  it("refreshes after a conflicting claim without showing success", async () => {
    h.claim.mockRejectedValue(new ApiError("OPERATOR_CLAIM_CONFLICT"));
    (button("Take case").props.onClick as () => void)(); await settle();
    expect(h.invalidate).toHaveBeenCalledOnce(); expect(h.navigate).not.toHaveBeenCalled();
    expect(elements(render()).some((e) => e.props.role === "alert")).toBe(true);
  });
  it("aborts a pending claim on route cleanup and suppresses stale success", async () => {
    let resolve!: (value: typeof ownedCase) => void; h.claim.mockImplementation(() => new Promise<typeof ownedCase>((done) => { resolve = done; }));
    const click = button("Take case").props.onClick as () => void;
    const cleanup = h.effects[1](); click();
    const signal = h.claim.mock.calls[0][1] as AbortSignal;
    if (typeof cleanup === "function") cleanup();
    h.caseId = "another-case"; render(); resolve(ownedCase); await settle();
    expect(signal.aborted).toBe(true); expect(h.invalidate).not.toHaveBeenCalled();
    expect(h.navigate).not.toHaveBeenCalled();
  });
  it("uses bounded pagination without linking to unclaimed detail", () => {
    h.queue.data = { items: [caseRecord], total: 51, offset: 0, limit: 50 };
    expect(button("Previous page").props.disabled).toBe(true);
    expect(button("Next page").props.disabled).toBe(false);
    expect(elements(render()).some((e) => e.props.to === "/operator/support-cases/case-id")).toBe(false);
    (button("Next page").props.onClick as () => void)();
    h.queue.data = { items: [caseRecord], total: 51, offset: 50, limit: 50 };
    expect(text(render())).toContain("Total cases: 51 · 51–51");
    expect(button("Next page").props.disabled).toBe(true);
    expect(button("Previous page").props.disabled).toBe(false);
    expect(h.queryOptions).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ["operator-cases", "session-1", "operator-id", 3, "available", "queue", 50] }));
    (button("Previous page").props.onClick as () => void)();
    expect(h.states[0]).toBe(0);
  });
  it.each([0, 1, 50, 51])("recovers a stale empty page when the queue shrinks to %j", (total) => {
    h.states[0] = 100;
    h.queue.data = { items: [], total, offset: 100, limit: 50 };
    const output = text(render());
    expect(output.includes("No cases awaiting review")).toBe(total === 0);
    expect(output).not.toContain("0–100");
    h.effects[0]();
    expect(h.states[0]).toBe(total > 50 ? 50 : 0);
  });
  it("suppresses success when canceled during cache reconciliation", async () => {
    let finish!: () => void;
    h.invalidate.mockImplementation(() => new Promise<void>((resolve) => { finish = resolve; }));
    const click = button("Take case").props.onClick as () => void;
    const cleanup = h.effects[1](); click(); await settle();
    expect(h.invalidate).toHaveBeenCalledOnce();
    if (typeof cleanup === "function") cleanup();
    finish(); await settle();
    expect(h.navigate).not.toHaveBeenCalled();
  });
  it("shows controlled owner-only detail failure with retry", () => {
    h.caseId = "foreign-case"; h.detail.error = new ApiError("CASE_NOT_FOUND");
    expect(elements(render()).some((e) => e.props.role === "alert")).toBe(true);
    (button("Retry").props.onClick as () => void)();
    expect(h.detail.refetch).toHaveBeenCalledOnce(); expect(h.queue.refetch).not.toHaveBeenCalled();
    expect(text(render())).not.toContain("Take case");
  });
  it("logs out an expired operator session", async () => {
    h.claim.mockRejectedValue(new ApiError("AUTH_REQUIRED"));
    (button("Take case").props.onClick as () => void)(); await settle(); expect(h.logout).toHaveBeenCalled();
  });
  it("lists assigned cases after refresh and resets view pagination", () => {
    h.states[0] = 50;
    (button("Assigned cases").props.onClick as () => void)();
    expect(h.states[0]).toBe(0);
    h.queue.data = { items: [{ ...caseRecord, status: "RESOLVED" }], total: 1, offset: 0, limit: 50 };
    expect(elements(render()).some((e) => e.props.to === "/operator/support-cases/case-id")).toBe(true);
    expect(text(render())).not.toContain("Take case");
    expect(h.queryOptions).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ["operator-cases", "session-1", "operator-id", 3, "assigned", "queue", 0] }));
    h.queue.data = { items: [], total: 0, offset: 0, limit: 50 };
    expect(text(render())).toContain("No assigned cases");
    (button("Available cases").props.onClick as () => void)();
    expect(h.states[1]).toBe("available");
  });
  it("isolates queries by session and uses detail only for a deep link", () => {
    h.caseId = "case-id"; h.sessionKey = "session-2";
    h.detail.data = ownedCase;
    expect(text(render())).toContain("Assigned to you");
    expect(h.queryOptions).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ["operator-cases", "session-2", "operator-id", 3, "available", "queue", 0], enabled: false }));
    expect(h.queryOptions).toHaveBeenLastCalledWith(expect.objectContaining({ queryKey: ["operator-cases", "session-2", "operator-id", 3, "case-id"], enabled: true }));
    expect(text(render())).toContain("Claim version1");
    expect(text(render())).not.toContain("Operator subject");
    expect(text(render())).not.toContain("operator-id");
    expect(text(render())).not.toContain("Take case");
  });
});
