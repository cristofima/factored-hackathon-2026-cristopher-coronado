import { describe, expect, it } from "vitest";
import type { FinancialTransaction } from "../api/financialClient";
import { canReportDispute, decimalString, decimalUnits, summarizeTransactions } from "./financial";

function transaction(overrides: Partial<FinancialTransaction> = {}): FinancialTransaction {
    return {
        id: "record", product_number: "account", date: "2026-06-01", amount: "1.0000",
        currency: "USD", type: "Deposit", status: "Approved", category: null,
        channel: null, merchant: null, ...overrides
    };
}

describe("financial movement policy", () => {
    it("shows dispute eligibility only for approved transactions within 365 days", () => {
        const now = Date.parse("2026-10-02T12:00:00Z");
        const cutoff = now - 365 * 24 * 60 * 60 * 1000;
        expect(canReportDispute(transaction({ date: new Date(cutoff).toISOString() }), now)).toBe(true);
        expect(canReportDispute(transaction({ date: new Date(cutoff - 1).toISOString() }), now)).toBe(false);
        expect(canReportDispute(transaction({ date: "2026-06-17T12:00:00", status: "Declined" }), now)).toBe(false);
        expect(canReportDispute(transaction({ date: "2026-06-17T12:00:00" }), now)).toBe(true);
        expect(canReportDispute(transaction({ date: "" }), now)).toBe(false);
        expect(canReportDispute(transaction({ date: "invalid" }), now)).toBe(false);
    });

    it("never offers a dispute on a runtime financial effect", () => {
        expect(canReportDispute(transaction({ sourceKind: "dispute_effect" }), Date.parse("2026-06-02"))).toBe(false);
    });
    it.each(["0.0000", "-0.0001", "9999999999999999.9999"])("preserves exact decimal %s", (value) => {
        expect(decimalString(decimalUnits(value))).toBe(value);
    });
    it.each(["NaN", "1e3", "1.00001", ""])("rejects invalid numeric value %s", (value) => {
        expect(() => decimalUnits(value)).toThrow("Invalid financial amount");
    });
    it("groups currencies and excludes pending, negative and unknown movements", () => {
        const summary = summarizeTransactions([
            transaction({ amount: "0.1000" }), transaction({ amount: "0.2000" }),
            transaction({ type: "Transfer", amount: "2.0000" }),
            transaction({ currency: "EUR", amount: "3.0000" }),
            transaction({ status: "Pending" }), transaction({ amount: "-1.0000" }),
            transaction({ type: "Adjustment" }), transaction({ type: null }),
        ]);
        expect(summary.excluded).toBe(4);
        expect(summary.currencies.get("USD")).toEqual({ inflow: 3000n, outflow: 20000n, count: 3 });
        expect(summary.currencies.get("EUR")).toEqual({ inflow: 30000n, outflow: 0n, count: 1 });
    });
    it("keeps an empty result distinct from unavailable data", () => {
        const summary = summarizeTransactions([]);
        expect(summary.excluded).toBe(0);
        expect(summary.currencies.size).toBe(0);
    });
});