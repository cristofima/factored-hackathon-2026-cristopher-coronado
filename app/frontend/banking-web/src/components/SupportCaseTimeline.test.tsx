import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { I18nextProvider } from "react-i18next";
import { createUiI18n } from "@/i18n";
import SupportCaseTimeline from "./SupportCaseTimeline";
import { formatDateTime } from "@/common/dateTime";

const event = { eventType: "OPERATOR_CLAIMED", actor: "operator", message: "Original stored audit", createdAt: "2026-10-04T10:30:00Z" };

describe("shared support case timeline", () => {
  it("wraps long audit text while retaining literal manual-note line breaks", () => {
    const note = "Original note\n" + "x".repeat(200);
    const html = renderToStaticMarkup(<I18nextProvider i18n={createUiI18n("en")}><SupportCaseTimeline events={[{ ...event, eventType: "UNKNOWN_EVENT", displayMessage: note }]} transactionId="txn" /></I18nextProvider>);
    expect(html).toContain("[overflow-wrap:anywhere]");
    expect(html).toContain("whitespace-pre-wrap");
    expect(html).toContain(note);
  });
  it.each([
    ["en", "Operator assigned", "no verdict or financial effect"],
    ["es", "Operador asignado", "ni un efecto financiero"],
    ["pt", "Operador atribuído", "nenhum veredito ou efeito financeiro"],
  ])("renders localized claim evidence in %s without mutating the audit", (locale, title, message) => {
    const html = renderToStaticMarkup(<I18nextProvider i18n={createUiI18n(locale)}><SupportCaseTimeline events={[event]} transactionId="txn" /></I18nextProvider>);
    expect(html).toContain(title);
    expect(html).toContain(message);
    expect(html).toContain("border-l-2 pl-3");
    expect(html).toContain(formatDateTime(event.createdAt, locale, "date-time-seconds"));
    expect(html).toContain(`dateTime="${event.createdAt}"`);
    expect(html).not.toContain("2026-10-04 10:30:00");
    expect(event.message).toBe("Original stored audit");
    expect(html).not.toContain("support-cases.");
  });
  it.each([
    ["en", "Customer approved the dispute", "You approved the dispute", "Assigned to you", "The customer’s consent"],
    ["es", "El cliente aprobó el reclamo", "Aprobaste el reclamo", "Asignado a ti", "El consentimiento del cliente"],
    ["pt", "O cliente aprovou a contestação", "Você aprovou a contestação", "Atribuído a você", "O consentimento do cliente"],
  ])("attributes consent to the customer and assignment to the operator in %s", (locale, approval, customerApproval, assignment, consent) => {
    const events = ["APPROVAL_REQUESTED", "APPROVAL_GRANTED", "APPROVAL_DECLINED", "OPERATOR_CLAIMED", "RECOMMENDATION_DISMISSED", "REVIEW_REQUIRED"].map(eventType => ({ ...event, eventType }));
    const render = (perspective: "customer" | "operator") => renderToStaticMarkup(
      <I18nextProvider i18n={createUiI18n(locale)}><SupportCaseTimeline events={events} transactionId="txn" perspective={perspective} /></I18nextProvider>,
    );
    const operator = render("operator");
    expect(operator).toContain(approval);
    expect(operator).toContain(assignment);
    expect(operator).toContain(consent);
    expect(operator).not.toContain(customerApproval);
    expect(operator).not.toContain("support-cases.");
    expect(render("customer")).toContain(customerApproval);
    expect(events.every(item => item.message === "Original stored audit")).toBe(true);
  });
  it.each(["customer", "operator"] as const)("preserves withdrawal attribution and historical no-credit wording for %s", perspective => {
    const html = renderToStaticMarkup(<I18nextProvider i18n={createUiI18n("en")}><SupportCaseTimeline perspective={perspective} events={[
      { ...event, eventType: "RESOLVED", message: "Case closed: withdrawn by customer" },
      { ...event, eventType: "RESOLVED", message: "Provisional credit issued; case resolved without manual review" },
    ]} transactionId="txn" /></I18nextProvider>);
    expect(html).toContain(perspective === "operator" ? "withdrawn by the customer" : "withdrawn by you");
    expect(html).toContain("no credit or financial movement recorded");
  });
  it.each(["customer", "operator"] as const)("preserves custom notes and unknown-event display fallbacks for %s", perspective => {
    const html = renderToStaticMarkup(<I18nextProvider i18n={createUiI18n("en")}><SupportCaseTimeline events={[
      { ...event, eventType: "RESOLVED", message: "Customer-written resolution note" },
      { ...event, eventType: "UNKNOWN_EVENT", message: "audit", displayMessage: "Safe display" },
    ]} transactionId="txn" perspective={perspective} /></I18nextProvider>);
    expect(html).toContain("Customer-written resolution note");
    expect(html).toContain("Safe display");
  });
});
