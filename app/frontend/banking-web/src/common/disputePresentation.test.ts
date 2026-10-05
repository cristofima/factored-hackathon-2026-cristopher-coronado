import { describe, expect, it } from "vitest";
import { createUiI18n } from "@/i18n";
import { formatProductAmount } from "./productAmount";
import { disputeProductLabel, disputeProtectionStatus, disputeSourceLabel, disputeTransactionStatus, formatStoredScore } from "./disputePresentation";

describe.each(["en", "es", "pt"])("persisted dispute presentation in %s", locale => {
  const t = createUiI18n(locale).t;
  it("uses controlled catalogs without translating arbitrary source text", () => {
    expect(disputeProductLabel("Savings Account", t)).toBe(t("Savings Account"));
    expect(disputeTransactionStatus("Approved", t)).toBe(t("transactions.statuses.Approved", { keySeparator: "." }));
    expect(disputeProtectionStatus(" BLOCKED ", t)).toBe(t("Blocked"));
    expect(disputeProtectionStatus(null, t)).toBe(t("Unavailable"));
    expect(disputeProductLabel("merchant text", t)).toBe(t("Unavailable"));
    expect(disputeSourceLabel("source", t)).not.toContain("operator.sources");
    expect(disputeSourceLabel("unrecognized", t)).toBe(t("Unavailable"));
    expect(disputeSourceLabel("dispute_effect", t)).not.toContain("operator.sources");
    expect(disputeTransactionStatus("merchant text", t)).toBe(t("Unavailable"));
    expect(disputeProtectionStatus("unknown", t)).toBe(t("Status unavailable"));
    expect(t("support-cases.resolution.dispute_rejected", { keySeparator: "." })).not.toContain("dispute_rejected");
  });
  it("preserves original decimal precision and distinguishes a zero signal", () => {
    const separator = locale === "en" ? "." : ",";
    expect(formatProductAmount("9007199254740993.1234", locale).replace(/[.,]/g, "")).toBe("90071992547409931234");
    expect(formatProductAmount("-0.0001", locale)).toBe(`-0${separator}0001`);
    expect(formatStoredScore("0", locale)).toBe("0");
    expect(formatStoredScore("invalid.00", locale)).toBe("invalid.00");
    expect(formatStoredScore("0.1234", locale)).toBe(`0${separator}1234`);
  });
});
