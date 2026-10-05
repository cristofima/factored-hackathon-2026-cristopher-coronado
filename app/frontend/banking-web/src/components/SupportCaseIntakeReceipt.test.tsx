import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import { describe, expect, it } from "vitest";
import { createUiI18n } from "@/i18n";
import type { SupportCase, SupportCaseEvent } from "@/models/SupportCase";
import SupportCaseIntakeReceipt from "./SupportCaseIntakeReceipt";

const base = { caseId: "case-ref", transactionId: "tx-ref", reason: "Customer's original explanation", status: "WAITING_USER_APPROVAL" } as SupportCase;
const event = (eventType: string, createdAt: string): SupportCaseEvent => ({ eventType, createdAt, actor: "customer", message: "Original audit" });
describe.each(["en", "es", "pt"])("customer readback in %s", locale => {
  const i18n = createUiI18n(locale);
  const render = (events: SupportCaseEvent[], status = base.status) => renderToStaticMarkup(<I18nextProvider i18n={i18n}><SupportCaseIntakeReceipt supportCase={{ ...base, status }} events={events} /></I18nextProvider>);
  it("reads persisted references and reason without manufacturing consent", () => {
    const html = render([]);
    expect(html).toContain("case-ref"); expect(html).toContain("tx-ref");
    expect(html).toContain("[overflow-wrap:anywhere]");
    expect(html).toContain("Customer&#x27;s original explanation");
    expect(html).toContain(i18n.t("Consent record unavailable"));
    expect(html).not.toContain("support-cases.");
    expect(html).not.toContain(i18n.t("support-cases.messages.APPROVAL_GRANTED", { keySeparator: "." }));
  });
  it.each(["APPROVAL_REQUESTED", "APPROVAL_GRANTED", "APPROVAL_DECLINED"])("reports recorded %s independently of case state", eventType => {
    for (const status of ["IN_REVIEW", "RESOLVED_INVALID", "PENDING_EFFECTS", "RESOLVED_VALID"] as const) {
      const html = render([event(eventType, "2026-10-04T12:00:00Z")], status);
      expect(html).toContain(i18n.t(`support-cases.messages.${eventType}`, { keySeparator: "." }));
      expect(html).toContain(i18n.t(`support-cases.status.${status}`, { keySeparator: "." }));
      expect(html).not.toContain("support-cases.");
    }
  });
  it("uses chronology rather than response order and leaves audit records unchanged", () => {
    const events = [event("APPROVAL_GRANTED", "2026-10-04T12:00:00Z"), event("APPROVAL_REQUESTED", "2026-10-04T11:00:00Z")];
    const original = JSON.stringify(events);
    expect(render(events)).toContain(i18n.t("support-cases.messages.APPROVAL_GRANTED", { keySeparator: "." }));
    expect(JSON.stringify(events)).toBe(original);
  });
});
