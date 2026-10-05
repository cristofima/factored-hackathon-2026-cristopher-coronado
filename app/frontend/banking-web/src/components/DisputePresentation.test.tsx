import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createUiI18n } from "@/i18n";
import type { OperatorCaseDetail } from "@/api/operatorDisputeClient";
import type { SupportCase } from "@/models/SupportCase";
import OperatorCaseActions from "./OperatorCaseActions";
import SupportCaseFinancialDetails from "./SupportCaseFinancialDetails";
const h = vi.hoisted(() => ({ locale: "en" }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: { id: "operator", locale: h.locale }, sessionKey: "session" }) }));
vi.mock("@tanstack/react-query", () => ({ useQueryClient: () => ({ invalidateQueries: vi.fn() }) }));
vi.mock("@/hooks/useProductCatalog", () => ({ useProductCatalog: () => ({ accounts: [], cards: [], loading: false, error: null, retry: vi.fn() }) }));
const effects = { movementId: "movement-ref", destinationProductId: "destination-ref", amount: "9007199254740993.1234", currency: "USD", balanceDelta: "-0.0001", executedAt: "2026-10-04T12:00:00Z" };
const base = { caseId: "case-ref", transactionId: "tx-ref", status: "RESOLVED_VALID", caseVersion: 7, evidenceVersion: 2, assignedOperatorSub: "operator", rationale: "Original rationale untouched", verdict: "valid", effects, productProtectionStatus: " Blocked ", evidence: { transactionId: "tx-ref", productId: "card-ref", productType: "Credit Card", amount: effects.amount, currency: "USD", transactionDate: effects.executedAt, status: "Approved", merchant: "Original Merchant", fraudScore: "0", isFraud: false, sourceKind: "source", city: "" }, eligibleDestinations: [{ productId: "destination-ref", productNumber: "12345", productType: "Savings Account", currency: "USD" }], cardProtection: { blocked: true, priorStatus: " ACTIVE ", rationale: "Original protection rationale", caseId: "case-ref", updatedAt: effects.executedAt, scope: "LOCAL_PRODUCT_ONLY" } } as OperatorCaseDetail;

describe.each(["en", "es", "pt"])("localized dispute context in %s", locale => {
  const i18n = createUiI18n(locale);
  const render = (node: React.ReactNode) => renderToStaticMarkup(<I18nextProvider i18n={i18n}>{node}</I18nextProvider>);
  beforeEach(() => { h.locale = locale; });
  it("groups fixed source evidence, routing, missing information and recorded effects", () => {
    const html = render(<OperatorCaseActions supportCase={{ ...base, status: "IN_REVIEW" }} />);
    const headings = ["Source evidence", "Stored routing signal", "Missing information", "Verdict and recorded effects"].map(key => html.indexOf(i18n.t(key)));
    expect(headings.every(index => index >= 0)).toBe(true);
    expect(headings).toEqual([...headings].sort((a, b) => a - b));
    for (const key of ["Credit Card", "Savings Account", "Blocked", "Active", "Unavailable", "This stored synthetic signal is for routing only, not an investigation or proof of legitimacy."]) expect(html).toContain(i18n.t(key));
    expect(html).toContain(i18n.t("transactions.statuses.Approved", { keySeparator: "." }));
    expect(html).toContain(i18n.t("operator.sources.source", { keySeparator: "." }));
    expect(html).toContain("Original Merchant"); expect(html).toContain("Original rationale untouched");
    expect(html).not.toContain("operator.evidence."); expect(html).not.toContain("operator.sources.");
    const missing = html.slice(html.indexOf(i18n.t("Missing information")), html.indexOf(i18n.t("Verdict and recorded effects")));
    for (const key of ["customerId", "country", "city", "responseCode"]) expect(missing).toContain(i18n.t(`operator.evidence.${key}`, { keySeparator: "." }));
    expect(missing).not.toContain(i18n.t("operator.evidence.fraudScore", { keySeparator: "." }));
  });
  it("keeps customer recorded-effect references, precision and separate local protection", () => {
    const html = render(<SupportCaseFinancialDetails supportCase={base as unknown as SupportCase} />);
    for (const ref of ["movement-ref", "destination-ref", "tx-ref", "Original rationale untouched", "Original protection rationale"]) expect(html).toContain(ref);
    expect(html).toContain(locale === "en" ? "9,007,199,254,740,993.1234" : "9.007.199.254.740.993,1234");
    expect(html).toContain(locale === "en" ? "-0.0001" : "-0,0001");
    expect(html).toContain("USD"); expect(html).toContain(i18n.t("Active"));
    expect(html).toContain(i18n.t("This recorded application movement does not confirm external settlement."));
  });
  it.each(["PENDING_EFFECTS", "RESOLVED_INVALID"] as const)("does not invent posting for %s", status => {
    const html = render(<SupportCaseFinancialDetails supportCase={{ ...base, status, effects: null, verdict: status === "RESOLVED_INVALID" ? "invalid" : "valid" } as unknown as SupportCase} />);
    expect(html).not.toContain("movement-ref");
    expect(html).toContain(i18n.t(status === "RESOLVED_INVALID" ? "Invalid verdict recorded. No restitution was posted for this case." : "Restitution is pending. No completed credit or balance change is confirmed."));
  });
});
