import { type ReactElement, type ReactNode, isValidElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SupportCaseFinancialDetails from "./SupportCaseFinancialDetails";
import type { SupportCase } from "@/models/SupportCase";
const h = vi.hoisted(() => ({ catalog: vi.fn(), retry: vi.fn() }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@/hooks/useProductCatalog", () => ({ useProductCatalog: h.catalog }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: { locale: "en" } }) }));
function text(node: ReactNode): string {
  if (Array.isArray(node)) return node.map(text).join("");
  if (isValidElement<Record<string, unknown>>(node)) return text(node.props.children as ReactNode);
  return typeof node === "string" || typeof node === "number" ? String(node) : "";
}
function elements(node: ReactNode): ReactElement<Record<string, unknown>>[] {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!isValidElement<Record<string, unknown>>(node)) return [];
  return [node, ...elements(node.props.children as ReactNode)];
}
const base = { caseId: "case-1", transactionId: "tx-1", status: "PENDING_EFFECTS", updatedAt: "2026-10-04", financialEffectsStatus: "PENDING" } as SupportCase;
beforeEach(() => { vi.clearAllMocks(); h.catalog.mockReturnValue({ accounts: [], cards: [], loading: false, error: null, retry: h.retry }); });
describe("truthful customer financial details", () => {
  it("describes pending effects without claiming completed restitution or protection", () => {
    const output = text(SupportCaseFinancialDetails({ supportCase: base }));
    expect(output).toContain("No completed credit or balance change is confirmed");
    expect(output).toContain("not the processor"); expect(output).not.toContain("Executed");
    expect(output).not.toContain("provisional");
  });
  it("wraps long financial references and preserves multiline rationale", () => {
    const transactionId = "tx-" + "x".repeat(200);
    const rationale = "First line\nSecond line";
    const output = SupportCaseFinancialDetails({ supportCase: { ...base, transactionId, rationale } });
    expect(text(output)).toContain(transactionId);
    expect(text(output)).toContain(rationale);
    expect(elements(output).some(e => String(e.props.className).includes("[overflow-wrap:anywhere]"))).toBe(true);
    expect(elements(output).some(e => e.props.className === "whitespace-pre-wrap" && text(e).includes(rationale))).toBe(true);
  });
  it("describes invalid verdict without a customer resolution action", () => {
    const output = text(SupportCaseFinancialDetails({ supportCase: { ...base, status: "RESOLVED_INVALID" } }));
    expect(output).toContain("No restitution was posted"); expect(output).not.toContain("Resolve dispute");
  });
  it("shows fetched balances verbatim and refreshes using case revision scope", () => {
    h.catalog.mockReturnValue({ accounts: [{ product_id: "destination", number: "123456", currency: "USD", balance: "137.25" }], cards: [], loading: false, error: null, retry: h.retry });
    const output = SupportCaseFinancialDetails({ supportCase: { ...base, status: "RESOLVED_VALID", financialEffectsStatus: "EXECUTED" } });
    expect(text(output)).toContain("137.25"); expect(text(output)).toContain("123456");
    expect(text(output)).toContain("Reload displayed balances");
    expect(text(output)).toContain("This only reloads balances; it does not issue a refund or change any balance.");
    expect(h.catalog).toHaveBeenCalledWith(JSON.stringify(["case-1", "RESOLVED_VALID", "EXECUTED", undefined]));
    const refresh = elements(output).find(e => typeof e.props.onClick === "function")!;
    (refresh.props.onClick as () => void)(); expect(h.retry).toHaveBeenCalledOnce();
  });
  it("masks fetched card numbers without masking bank account numbers", () => {
    h.catalog.mockReturnValue({ accounts: [{ product_id: "bank", number: "1234567890123456", currency: "USD", balance: "30" }], cards: [{ product_id: "card", number: "4111111111111234", currency: "USD", balance: "40" }], loading: false, error: null, retry: h.retry });
    const output = text(SupportCaseFinancialDetails({ supportCase: base }));
    expect(output).toContain("1234567890123456");
    expect(output).toContain("4111 **** **** 1234");
    expect(output).not.toContain("4111111111111234");
  });
  it("does not refresh balances for unrelated audit revisions", () => {
    SupportCaseFinancialDetails({ supportCase: base });
    SupportCaseFinancialDetails({ supportCase: { ...base, updatedAt: "2026-10-05" } });
    expect(h.catalog.mock.calls[0][0]).toBe(h.catalog.mock.calls[1][0]);
  });
  it("shows recorded posting, rationale and nullable protection audit without invented effects", () => {
    const output = text(SupportCaseFinancialDetails({ supportCase: { ...base, status: "RESOLVED_VALID", verdict: "valid", rationale: "Reviewed original facts", effects: { movementId: "movement-1", destinationProductId: "destination-1", amount: "10.00", currency: "USD", balanceDelta: "10.00", executedAt: "2026-10-04T12:00:00Z" }, cardProtection: { blocked: true, priorStatus: null, rationale: "Protection reason", caseId: "prior-case", updatedAt: "2026-10-04T12:00:00Z", scope: "LOCAL_PRODUCT_ONLY" } } }));
    expect(output).toContain("movement-1"); expect(output).toContain("destination-1");
    expect(output).toContain("Recorded balance adjustment: 10.00 USD");
    expect(output).toContain("Reviewed original facts"); expect(output).toContain("Protection reason");
    expect(output).toContain("Recorded prior status: Unavailable"); expect(output).toContain("prior-case");
    expect(output).toContain("not the processor"); expect(output).not.toContain("provisional");
  });
  it("refreshes balances when a recorded posting arrives", () => {
    SupportCaseFinancialDetails({ supportCase: base });
    SupportCaseFinancialDetails({ supportCase: { ...base, effects: { movementId: "movement-1", destinationProductId: "destination", amount: "10", currency: "USD", balanceDelta: "10", executedAt: "2026-10-04T12:00:00Z" } } });
    expect(h.catalog.mock.calls[0][0]).not.toBe(h.catalog.mock.calls[1][0]);
  });
  it("shows unavailable balance errors instead of reconstructing a balance", () => {
    h.catalog.mockReturnValue({ accounts: [], cards: [], loading: false, error: "Balances are unavailable", retry: h.retry });
    const output = SupportCaseFinancialDetails({ supportCase: base });
    expect(elements(output).find(e => e.props.role === "alert")).toBeDefined();
    expect(text(output)).toContain("Balances are unavailable");
  });
});
