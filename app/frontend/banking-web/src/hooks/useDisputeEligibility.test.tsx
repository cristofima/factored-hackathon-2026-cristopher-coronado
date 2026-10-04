import { beforeEach, describe, expect, it, vi } from "vitest";
import { useDisputeEligibility, activeTransactionCases } from "./useDisputeEligibility";
import DisputeReportAction from "@/components/DisputeReportAction";
import ReportDisputeDialog from "@/components/ReportDisputeDialog";
import type { SupportCase } from "@/models/SupportCase";
import type { FinancialTransaction } from "@/api/financialClient";

const harness = vi.hoisted(() => ({
  states: [] as unknown[], cursor: 0, deps: [] as unknown[][],
  effects: [] as Array<() => void>, cleanups: [] as Array<(() => void) | undefined>,
  user: { id: "customer-a" } as { id: string } | null, sessionKey: 1,
  list: vi.fn(),
}));
vi.mock("react", async (original) => ({
  ...await original<typeof import("react")>(),
  useState: (initial: unknown) => {
    const index = harness.cursor++;
    if (!(index in harness.states)) harness.states[index] = initial;
    return [harness.states[index], (value: unknown) => {
      harness.states[index] = typeof value === "function" ? value(harness.states[index]) : value;
    }];
  },
  useCallback: (callback: unknown) => callback,
  useEffect: (effect: () => void | (() => void), deps: unknown[]) => {
    const index = harness.cursor++;
    if (!harness.deps[index] || deps.some((dep, i) => !Object.is(dep, harness.deps[index][i]))) {
      harness.deps[index] = deps;
      harness.effects.push(() => { harness.cleanups[index]?.(); harness.cleanups[index] = effect() || undefined; });
    }
  },
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: harness.user, sessionKey: harness.sessionKey }) }));
vi.mock("@/api/disputeClient", () => ({ listSupportCases: harness.list }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@/components/ReportDisputeDialog", () => ({ default: () => null }));

const caseFor = (status: string, transactionId = "tx"): SupportCase => ({
  caseId: `case-${status}`, transactionId, status, productNumber: "account", reason: "customer reason",
  triageOutcome: null, resolutionOutcome: null, resolutionNotes: null, recommendationType: null,
  recommendationRationale: null, recommendationOptedOut: false, openedAt: "", updatedAt: "", resolvedAt: null,
});
const record: FinancialTransaction = { id: "tx", product_number: "account", date: new Date().toISOString(), amount: "1", currency: "USD", type: "Deposit", category: null, channel: null, merchant: null, status: "Approved" };
function useRender(enabled = true) { harness.cursor = 0; return useDisputeEligibility(enabled); }
function effects() { harness.effects.splice(0).forEach(effect => effect()); }
async function settle() { await Promise.resolve(); await Promise.resolve(); }
beforeEach(() => {
  harness.cleanups.forEach(cleanup => cleanup?.());
  vi.resetAllMocks();
  harness.states = []; harness.deps = []; harness.effects = []; harness.cleanups = [];
  harness.user = { id: "customer-a" }; harness.sessionKey = 1;
});

describe("customer-scoped dispute reporting", () => {
  it("fetches the complete list once and replaces every active row with a case link", async () => {
    harness.list.mockResolvedValue([caseFor("WAITING_USER_APPROVAL"), caseFor("RESOLVED", "closed")]);
    const loading = useRender();
    expect(DisputeReportAction({ record, eligibility: loading })).toBeNull();
    effects(); await settle();
    const ready = useRender(); effects();
    expect(ready.status).toBe("ready");
    expect(ready.activeCases.has("closed")).toBe(false);
    for (let row = 0; row < 20; row++) {
      const action = DisputeReportAction({ record, eligibility: ready });
      expect(action?.props.to).toBe("/support-cases/case-WAITING_USER_APPROVAL");
      expect(action?.props.children).toBe("View existing dispute");
    }
    expect(harness.list).toHaveBeenCalledOnce();
  });
  it.each(["OPEN", "IN_REVIEW", "ESCALATED_TO_REVIEW", "UNKNOWN_STATUS"])("treats %s as active without changing stored records", (status) => {
    const item = caseFor(status);
    expect(activeTransactionCases([item]).get("tx")).toBe(item);
    expect(item.status).toBe(status);
  });
  it("allows resolved or missing cases, preserving Approved and 365-day policy including deposits", async () => {
    harness.list.mockResolvedValue([caseFor("RESOLVED")]); useRender(); effects(); await settle();
    const eligibility = useRender();
    expect(DisputeReportAction({ record, eligibility })?.type).toBe(ReportDisputeDialog);
    expect(DisputeReportAction({ record: { ...record, id: "missing" }, eligibility })?.type).toBe(ReportDisputeDialog);
    expect(DisputeReportAction({ record: { ...record, status: "Declined" }, eligibility })).toBeNull();
    expect(DisputeReportAction({ record: { ...record, date: "2000-01-01" }, eligibility })).toBeNull();
  });
  it("refreshes eligibility after creation and scopes dialog instances to the authenticated session", async () => {
    harness.list.mockResolvedValueOnce([]).mockResolvedValueOnce([caseFor("OPEN")]).mockResolvedValue([]);
    useRender(); effects(); await settle();
    const ready = useRender();
    const originalAction = DisputeReportAction({ record, eligibility: ready });
    expect(originalAction?.props.onCasesChanged).toBe(ready.refresh);
    ready.refresh();
    expect(DisputeReportAction({ record, eligibility: useRender() })).toBeNull();
    effects(); await settle();
    expect(DisputeReportAction({ record, eligibility: useRender() })?.props.to).toBe("/support-cases/case-OPEN");
    harness.user = { id: "customer-b" }; harness.sessionKey++;
    expect(DisputeReportAction({ record, eligibility: useRender() })).toBeNull();
    effects(); await settle();
    expect(DisputeReportAction({ record, eligibility: useRender() })?.key).not.toBe(originalAction?.key);
    expect(harness.list).toHaveBeenCalledTimes(3);
  });
  it("fails closed on error and retry until the complete list succeeds", async () => {
    harness.list.mockRejectedValueOnce(new Error("unavailable")).mockResolvedValueOnce([]);
    useRender(); effects(); await settle();
    const error = useRender();
    expect(error.status).toBe("error");
    expect(DisputeReportAction({ record, eligibility: error })).toBeNull();
    error.refresh();
    expect(useRender().status).toBe("loading"); effects(); await settle();
    expect(useRender().status).toBe("ready");
    expect(harness.list).toHaveBeenCalledTimes(2);
  });
  it("immediately hides prior-user actions, aborts old requests and ignores stale completion", async () => {
    let complete!: (cases: SupportCase[]) => void;
    harness.list.mockResolvedValue([]).mockImplementationOnce(() => new Promise(resolve => { complete = resolve; }));
    useRender(); effects(); const signal = harness.list.mock.calls[0][0] as AbortSignal;
    harness.user = { id: "customer-b" }; harness.sessionKey++;
    const switched = useRender();
    expect(switched.status).toBe("loading");
    expect(DisputeReportAction({ record, eligibility: switched })).toBeNull();
    effects(); expect(signal.aborted).toBe(true);
    complete([caseFor("OPEN")]); await settle();
    expect(useRender().activeCases.size).toBe(0);
    expect(useRender().status).toBe("ready");
    harness.sessionKey++;
    expect(useRender().status).toBe("loading"); effects(); await settle();
    harness.user = null; useRender(); effects(); await settle();
    expect(useRender().status).toBe("loading");
    expect(harness.list).toHaveBeenCalledTimes(3);
  });
  it("rejects cached ready data immediately on identity change and skips non-report entrypoints", async () => {
    harness.list.mockResolvedValue([caseFor("OPEN")]); useRender(); effects(); await settle();
    expect(useRender().activeCases.size).toBe(1);
    harness.user = { id: "customer-b" };
    expect(useRender().activeCases.size).toBe(0);
    expect(useRender().status).toBe("loading"); effects(); await settle();
    expect(useRender(false).activeCases.size).toBe(0); effects();
    expect(harness.list).toHaveBeenCalledTimes(2);
  });
});
