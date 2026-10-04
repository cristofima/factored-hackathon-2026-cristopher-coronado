import { isValidElement, type ReactElement, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ReportDisputeDialog from "./ReportDisputeDialog";
import { Dialog } from "@/components/ui/dialog";
import { ApiError } from "@/api/errors";

const harness = vi.hoisted(() => ({
  states: [] as unknown[], refs: [] as Array<{ current: unknown }>, cursor: 0,
  effects: [] as Array<() => void | (() => void)>,
  list: vi.fn(), create: vi.fn(), navigate: vi.fn(), refresh: vi.fn(),
}));
vi.mock("react", async (original) => ({
  ...await original<typeof import("react")>(),
  useState: (initial: unknown) => {
    const index = harness.cursor++;
    if (!(index in harness.states)) harness.states[index] = initial;
    return [harness.states[index], (value: unknown) => { harness.states[index] = value; }];
  },
  useRef: (initial: unknown) => {
    const index = harness.cursor++;
    return harness.refs[index] ??= { current: initial };
  },
  useEffect: (effect: () => void | (() => void)) => { harness.effects.push(effect); },
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => harness.navigate }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({}) }));
vi.mock("@/api/disputeClient", () => ({ listSupportCases: harness.list, openSupportCase: harness.create }));

type Element = ReactElement<Record<string, unknown>>;
function elements(node: ReactNode): Element[] {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!isValidElement<Record<string, unknown>>(node)) return [];
  return [node, ...elements(node.props.children as ReactNode)];
}
function render() { harness.cursor = 0; return ReportDisputeDialog({ transactionId: "tx", onCasesChanged: harness.refresh }); }
function find(predicate: (element: Element) => boolean) {
  const control = elements(render()).find(predicate);
  if (!control) throw new Error("Missing control");
  return control;
}
function reason(value = "  original reason  ") {
  (find(element => typeof element.props.onChange === "function").props.onChange as (event: { target: { value: string } }) => void)({ target: { value } });
}
function submit() {
  return (find(element => element.props.children === "Submit dispute").props.onClick as () => Promise<void>)();
}
beforeEach(() => {
  vi.resetAllMocks(); harness.states = []; harness.refs = []; harness.effects = [];
  harness.list.mockResolvedValue([]); harness.create.mockResolvedValue({ caseId: "new" });
});

describe("dispute submission revalidation", () => {
  it.each(["OPEN", "IN_REVIEW", "WAITING_USER_APPROVAL", "ESCALATED_TO_REVIEW"])("links to an existing %s case without posting", async (status) => {
    harness.list.mockResolvedValue([{ caseId: "existing", transactionId: "tx", status }]);
    reason(); await submit();
    expect(harness.create).not.toHaveBeenCalled();
    expect(harness.navigate).toHaveBeenCalledWith("/support-cases/existing");
    expect(harness.refresh).toHaveBeenCalledOnce();
  });
  it("creates after resolved cases, refreshes once, and preserves the trimmed customer reason", async () => {
    harness.list.mockResolvedValue([{ caseId: "closed", transactionId: "tx", status: "RESOLVED" }]);
    reason(); await submit();
    expect(harness.create).toHaveBeenCalledWith("tx", "original reason", expect.any(AbortSignal));
    expect(harness.navigate).toHaveBeenCalledWith("/support-cases/new");
    expect(harness.refresh).toHaveBeenCalledOnce();
    expect(elements(render()).some(element => element.props.children === "Dispute processing limitations")).toBe(false);
  });
  it("fails closed when list revalidation fails, retains an actionable error and retries revalidation", async () => {
    harness.list.mockRejectedValueOnce(new Error("private server detail"));
    reason(); await submit();
    expect(harness.create).not.toHaveBeenCalled();
    expect(harness.refresh).not.toHaveBeenCalled();
    expect(find(element => element.props.role === "alert").props.children).toBe("Could not open the dispute");
    expect(find(element => element.props.children === "Submit dispute").props.disabled).toBe(false);
    await submit();
    expect(harness.list).toHaveBeenCalledTimes(2);
    expect(harness.create).toHaveBeenCalledOnce();
  });
  it("reloads the complete list after a duplicate creation conflict and opens the existing case", async () => {
    harness.list.mockResolvedValueOnce([]).mockResolvedValueOnce([{ caseId: "raced", transactionId: "tx", status: "OPEN" }]);
    harness.create.mockRejectedValue(new ApiError("DISPUTE_ALREADY_ACTIVE"));
    reason(); await submit();
    expect(harness.list).toHaveBeenCalledTimes(2);
    expect(harness.create).toHaveBeenCalledOnce();
    expect(harness.navigate).toHaveBeenCalledWith("/support-cases/raced");
    expect(harness.refresh).toHaveBeenCalledOnce();
  });
  it.each(["unavailable", "missing"])("retains safe conflict feedback when reload is %s and permits revalidated retry", async (state) => {
    harness.list.mockResolvedValueOnce([]);
    if (state === "unavailable") harness.list.mockRejectedValueOnce(new Error("private detail"));
    else harness.list.mockResolvedValueOnce([]);
    harness.create.mockRejectedValue(new ApiError("DISPUTE_ALREADY_ACTIVE"));
    reason(); await submit();
    expect(find(element => element.props.role === "alert").props.children).toBe("An active dispute already exists. Retry to open the existing case.");
    expect(harness.refresh).not.toHaveBeenCalled();
    expect(harness.navigate).not.toHaveBeenCalled();
    harness.list.mockResolvedValue([{ caseId: "raced", transactionId: "tx", status: "OPEN" }]);
    await submit();
    expect(harness.create).toHaveBeenCalledOnce();
    expect(harness.navigate).toHaveBeenCalledWith("/support-cases/raced");
  });
  it("retains controlled creation errors without unmounting the dialog", async () => {
    harness.create.mockRejectedValue(new Error("server detail")); reason(); await submit();
    expect(find(element => element.props.role === "alert").props.children).toBe("Could not open the dispute");
    expect(harness.refresh).not.toHaveBeenCalled();
    expect(harness.navigate).not.toHaveBeenCalled();
  });
  it("blocks duplicate submits and dismissal while pending", async () => {
    let complete!: (cases: unknown[]) => void;
    harness.list.mockImplementation(() => new Promise(resolve => { complete = resolve; }));
    (find(element => element.type === Dialog).props.onOpenChange as (open: boolean) => void)(true);
    reason(); const pending = submit(); await submit();
    expect(harness.list).toHaveBeenCalledOnce();
    expect(find(element => typeof element.props.onChange === "function").props.disabled).toBe(true);
    reason("changed while revalidation was pending");
    (find(element => element.type === Dialog).props.onOpenChange as (open: boolean) => void)(false);
    expect(find(element => element.type === Dialog).props.open).toBe(true);
    complete([]); await pending;
    expect(harness.create).toHaveBeenCalledWith("tx", "original reason", expect.any(AbortSignal));
  });
  it.each(["list", "creation"])("aborts on scope-key unmount during %s and prevents stale navigation/refresh", async (phase) => {
    let complete!: (value: unknown) => void;
    harness[phase === "list" ? "list" : "create"].mockImplementation(() => new Promise(resolve => { complete = resolve; }));
    reason(); const cleanup = harness.effects[0](); const pending = submit();
    await Promise.resolve(); await Promise.resolve();
    const signal = harness.list.mock.calls[0][0] as AbortSignal;
    if (cleanup) cleanup();
    expect(signal.aborted).toBe(true);
    complete(phase === "list" ? [] : { caseId: "stale" }); await pending;
    expect(harness.navigate).not.toHaveBeenCalled();
    expect(harness.refresh).not.toHaveBeenCalled();
    if (phase === "list") expect(harness.create).not.toHaveBeenCalled();
  });
});
