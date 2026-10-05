import { describe, expect, it } from "vitest";
import { readToolCase, readToolPreview, toolOutputFailed, toolProgressKey } from "./responseItems";

const supportCase = {
  caseId: "owned-case", transactionId: "transaction", productNumber: null,
  reason: "Customer reason", status: "WAITING_USER_APPROVAL", triageOutcome: null,
  resolutionOutcome: null, resolutionNotes: null, recommendationType: null,
  recommendationRationale: null, recommendationOptedOut: false,
  openedAt: "2026-10-04", updatedAt: "2026-10-04", resolvedAt: null,
};

const preview = { previewToken: "signed", transactionId: "transaction", reason: "Original reason", expiresAt: "2026-10-04T10:10:00Z", transaction: { id: "transaction", country: "CO", city: null, description: null, recipientName: "Óptica Visión", status: "Approved" } };
describe("Responses dispute previews", () => {
  it.each([preview, JSON.stringify(preview), { content: [{ type: "text", text: JSON.stringify(preview) }] }])("parses structured signed previews without a case receipt", output => {
    expect(readToolPreview(output)).toEqual(preview);
    expect(readToolCase(output)).toBeNull();
  });
  it.each([null, "Preview prepared", { ...preview, transaction: { id: "foreign" } }, { ...preview, expiresAt: "invalid" }, { isError: true, content: [{ type: "text", text: JSON.stringify(preview) }] }])("rejects unsafe previews", output => {
    expect(readToolPreview(output)).toBeNull();
  });
  it("strips internal fraud and receipt fields", () => {
    expect(readToolPreview({ ...preview, caseId: "not-created", status: "IN_REVIEW", transaction: { ...preview.transaction, fraud_score: 0.2, is_fraud: true } })).toEqual(preview);
  });
});
describe("Responses tool outputs", () => {
  it.each([supportCase, JSON.stringify(supportCase), { content: [{ type: "text", text: JSON.stringify(supportCase) }] }])("accepts a complete persisted case", (output) => {
    expect(readToolCase(output)).toEqual(supportCase);
  });
  it.each([null, "Case owned-case opened", { caseId: "owned-case" }, { ...supportCase, error: "denied" }, { isError: true, content: [{ type: "text", text: JSON.stringify(supportCase) }] }])("rejects incomplete, prose and error-marked cases", (output) => {
    expect(readToolCase(output)).toBeNull();
  });
  it.each([{ isError: true }, { error: "denied" }, JSON.stringify({ error: "denied" })])("recognizes structured failures", (output) => {
    expect(toolOutputFailed(output)).toBe(true);
  });
  it.each([supportCase, "error in customer reason", { error: null }, undefined])("does not infer failures from prose or business status", (output) => {
    expect(toolOutputFailed(output)).toBe(false);
  });
  it.each([
    [undefined, null], ["handoff_to_transaction", null], ["triage", null],
    ["reportTransactionDispute", "Processing support case"],
    ["getTransactions", "Looking up transactions"], ["getAccountBalance", "Looking up account information"],
    ["otherTool", "Processing request"],
  ])("maps %s to safe progress text", (name, key) => {
    expect(toolProgressKey(name ?? undefined)).toBe(key);
  });
});
