import { type ReactElement, type ReactNode, isValidElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import OperatorCaseActions from "./OperatorCaseActions";
import type { OperatorCaseDetail } from "@/api/operatorDisputeClient";
const h = vi.hoisted(() => ({ states: [] as unknown[], cursor: 0, refs: [] as Array<{current: unknown}>, refCursor: 0, effects: [] as Array<() => void | (() => void)>, adjudicate: vi.fn(), retry: vi.fn(), protect: vi.fn(), invalidate: vi.fn(), logout: vi.fn(), session: "session-1" }));
vi.mock("react", async original => ({ ...await original<typeof import("react")>(),
  useState: (initial: unknown) => { const i = h.cursor++; if (!(i in h.states)) h.states[i] = initial; return [h.states[i], (value: unknown) => { h.states[i] = value; }]; },
  useRef: (initial: unknown) => { const i = h.refCursor++; return h.refs[i] ?? (h.refs[i] = { current: initial }); },
  useEffect: (effect: () => void | (() => void)) => h.effects.push(effect),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: { id: "operator", identityVersion: 4, locale: "en" }, sessionKey: h.session, logout: h.logout }) }));
vi.mock("@tanstack/react-query", () => ({ useQueryClient: () => ({ invalidateQueries: h.invalidate }) }));
vi.mock("@/api/operatorDisputeClient", () => ({ adjudicateOperatorCase: h.adjudicate, retryOperatorEffects: h.retry, protectOperatorCard: h.protect }));
type Element = ReactElement<Record<string, unknown>>;
function elements(node: ReactNode): Element[] { if (Array.isArray(node)) return node.flatMap(elements); if (!isValidElement<Record<string, unknown>>(node)) return []; return [node, ...elements(node.props.children as ReactNode)]; }
function text(node: ReactNode): string { if (Array.isArray(node)) return node.map(text).join(""); if (isValidElement<Record<string, unknown>>(node)) return text(node.props.children as ReactNode); return typeof node === "string" || typeof node === "number" ? String(node) : ""; }
const base = { caseId: "case", status: "IN_REVIEW", caseVersion: 7, evidenceVersion: 2, productProtectionStatus: "Active", assignedOperatorSub: "operator", evidence: { transactionId: "tx", productId: "card", productType: "Debit Card", amount: "10.00", currency: "USD", transactionDate: "2026-10-04T12:00:00Z" }, eligibleDestinations: [] } as OperatorCaseDetail;
let supportCase: OperatorCaseDetail;
function render(): Element { h.cursor = 0; h.refCursor = 0; h.effects = []; return OperatorCaseActions({ supportCase }); }
function button(label: string): Element { const result = elements(render()).find(e => typeof e.props.onClick === "function" && text(e) === label); if (!result) throw new Error("Missing " + label); return result; }
function click(label: string): void { (button(label).props.onClick as () => void)(); }
function reason(value: string): void { const field = elements(render()).find(e => e.props.id === "operator-rationale")!; (field.props.onChange as (e: unknown) => void)({ target: { value } }); }
beforeEach(() => { vi.clearAllMocks(); h.states = []; h.refs = []; h.session = "session-1"; supportCase = { ...base }; h.adjudicate.mockResolvedValue(base); h.retry.mockResolvedValue(base); h.protect.mockResolvedValue(base); h.invalidate.mockResolvedValue(undefined); });
describe("assigned operator adjudication", () => {
  it("distinguishes missing evidence from unavailable destinations", () => {
    supportCase = { ...base, caseVersion: 0, evidenceVersion: 0, evidence: null };
    const output = render();
    expect(text(output)).toContain("Verified evidence is unavailable. No financial completion is confirmed.");
    expect(elements(output).some(e => e.props.id === "restitution-destination")).toBe(false);
    expect(text(output)).not.toContain("No eligible destination");
    expect(button("Valid dispute").props.disabled).toBe(true);
  });
  it("does not describe restitution as pending before a valid verdict", () => {
    const output = render();
    expect(text(output)).toContain("No eligible destination");
    expect(text(output)).not.toContain("Restitution remains pending");
    expect(text(output)).toContain("Stored transaction data supports review; it does not prove the dispute is valid.");
  });
  it("requires rationale, evidence and versions, never customer authority", () => {
    expect(button("Valid dispute").props.disabled).toBe(true); reason("reviewed evidence"); expect(button("Valid dispute").props.disabled).toBe(false);
    supportCase = { ...base, evidence: null }; expect(button("Valid dispute").props.disabled).toBe(true);
    supportCase = { ...base, assignedOperatorSub: "someone-else" }; expect(text(render())).not.toContain("Mandatory rationale");
  });
  it("confirms versioned valid verdict before sending the request", async () => {
    reason("verified rationale"); click("Valid dispute"); expect(h.adjudicate).not.toHaveBeenCalled(); expect(text(render())).toContain("Case version: 7");
    await (button("Confirm").props.onClick as () => Promise<void>)();
    expect(h.adjudicate).toHaveBeenCalledWith("case", { verdict: "valid", rationale: "verified rationale", expected_case_version: 7, expected_evidence_version: 2 }, expect.any(AbortSignal));
    expect(h.invalidate).toHaveBeenCalledWith({ queryKey: ["operator-cases", "session-1", "operator", 4] }); expect(h.protect).not.toHaveBeenCalled();
  });
  it("allows a verdict to persist but requires an explicit destination before retry execution", () => {
    supportCase = { ...base, eligibleDestinations: [{productId: "a", productNumber: "100", productType: "Savings Account", currency: "USD"}, {productId: "b", productNumber: "200", productType: "Savings Account", currency: "USD"}] };
    reason("verified"); expect(button("Valid dispute").props.disabled).toBe(false); expect(button("Invalid dispute").props.disabled).toBe(false);
        supportCase = { ...supportCase, status: "PENDING_EFFECTS" };
        expect(button("Retry financial effects").props.disabled).toBe(true);
        const select = elements(render()).find(e => e.props.id === "restitution-destination")!; (select.props.onChange as (e: unknown) => void)({target: {value: "b"}}); expect(button("Retry financial effects").props.disabled).toBe(false);
  });
  it("masks card numbers in destination confirmation", () => {
    supportCase = { ...base, eligibleDestinations: [{ productId: "card", productNumber: "4111111111111111", productType: "Credit Card", currency: "USD" }] };
    reason("verified"); click("Valid dispute");
    const rendered = text(render());
    expect(rendered).not.toContain("4111111111111111"); expect(rendered).toContain("1111");
  });
  it("does not describe ambiguous destinations as unavailable in confirmation", () => {
    supportCase = { ...base, eligibleDestinations: [{ productId: "a", productNumber: "100", productType: "Savings Account", currency: "USD" }, { productId: "b", productNumber: "200", productType: "Savings Account", currency: "USD" }] };
    reason("verified"); click("Valid dispute");
    expect(text(render())).toContain("Select an eligible destination");
    expect(text(render())).not.toContain("No eligible destination. Restitution remains pending.");
  });
  it("keeps destination-unavailable pending without false completion", () => { supportCase = { ...base, status: "PENDING_EFFECTS", effectCode: "DESTINATION_UNAVAILABLE" }; expect(text(render())).toContain("No completed credit or balance change is confirmed"); expect(text(render())).not.toContain("restitution posted"); expect(button("Retry financial effects").props.disabled).toBe(false); });
  it("shows actual posting references and separate protection scope", () => { supportCase = { ...base, status: "RESOLVED_VALID", effects: {movementId: "REFUND-1", destinationProductId: "savings", amount: "10.00", currency: "USD", balanceDelta: "10.00", executedAt: "2026-10-04T12:00:00Z"} }; expect(text(render())).toContain("REFUND-1"); expect(text(render())).toContain("Recorded balance adjustment: 10.00 USD"); expect(text(render())).toContain("not the processor"); expect(text(render())).toContain("No recorded protection action"); });
  it.each([null, undefined, "", "  "])("disables protection without actual product state %j", productProtectionStatus => {
    supportCase = { ...base, productProtectionStatus }; reason("reviewed");
    expect(button("Block in application").props.disabled).toBe(true);
    expect(text(render())).toContain("Current card state: Unavailable");
  });
  it("uses actual blocked state, not recorded action or transaction evidence, for unblocking", async () => {
    supportCase = { ...base, productProtectionStatus: "Blocked", cardProtection: { blocked: false, priorStatus: null, rationale: "Earlier action", caseId: "earlier-case", updatedAt: "2026-10-04T12:00:00Z", scope: "LOCAL_PRODUCT_ONLY" } };
    reason("Protection reviewed"); click("Unblock in application");
    expect(text(render())).toContain("Current card state: Blocked");
    expect(text(render())).toContain("Recorded prior status: Unavailable");
    await (button("Confirm").props.onClick as () => Promise<void>)();
    expect(h.protect).toHaveBeenCalledWith("case", { expected_case_version: 7, rationale: "Protection reviewed", blocked: false }, expect.any(AbortSignal));
    expect(h.adjudicate).not.toHaveBeenCalled();
  });
  it("blocks an actual active card despite a prior recorded block", async () => {
    supportCase = { ...base, cardProtection: { blocked: true, priorStatus: "Active", rationale: "Earlier action", caseId: "earlier-case", updatedAt: "2026-10-04T12:00:00Z", scope: "LOCAL_PRODUCT_ONLY" } };
    reason("Current protection reviewed"); click("Block in application");
    expect(text(render())).toContain("Current card state: Active");
    await (button("Confirm").props.onClick as () => Promise<void>)();
    expect(h.protect.mock.calls[0][1]).toMatchObject({ blocked: true });
  });
  it("aborts pending actions when the session scope is disposed", async () => { let resolve!: (value: unknown) => void; h.adjudicate.mockImplementation(() => new Promise(r => { resolve = r; })); reason("verified"); click("Valid dispute"); const action = (button("Confirm").props.onClick as () => Promise<void>)(); const cleanup = h.effects[0](); if (typeof cleanup === "function") cleanup(); expect(h.adjudicate.mock.calls[0][2].aborted).toBe(true); resolve(base); await action; expect(h.invalidate).not.toHaveBeenCalled(); });
});
