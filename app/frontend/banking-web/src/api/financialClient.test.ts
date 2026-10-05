import { afterEach, describe, expect, it, vi } from "vitest";
import { getTransactions } from "./financialClient";

vi.mock("./authToken", () => ({ getAuthToken: () => "test-only-token" }));

const record = (id: string) => ({ id, amount: 1.0, currency: "USD" });
const page = (items: ReturnType<typeof record>[], total: number) => new Response(JSON.stringify({ items, total }));

afterEach(() => vi.unstubAllGlobals());

describe("Transaction API pagination", () => {
    it("loads every page and carries the inclusive window and abort signal", async () => {
        const fetch = vi.fn().mockResolvedValueOnce(page(Array.from({ length: 100 }, (_, i) => record(String(i))), 101))
            .mockResolvedValueOnce(page([record("100")], 101));
        vi.stubGlobal("fetch", fetch);
        const signal = new AbortController().signal;
        expect(await getTransactions("account", "2026-06-01", "2026-06-17", signal)).toHaveLength(101);
        expect(fetch.mock.calls[1][0]).toContain("offset=100");
        expect(fetch.mock.calls[0][0]).toContain("start_date=2026-06-01&end_date=2026-06-17");
        expect(fetch.mock.calls[0][1].signal).toBe(signal);
    });
    it.each([
        [page([record("1")], 2), page([record("2")], 3)],
        [page([record("1")], 2), page([record("1")], 2)],
        [page([], 1)],
    ])("rejects inconsistent or duplicate pages", async (...pages) => {
        const fetch = vi.fn();
        for (const response of pages) fetch.mockResolvedValueOnce(response);
        vi.stubGlobal("fetch", fetch);
        await expect(getTransactions("account", "2026-06-01", "2026-06-17", new AbortController().signal)).rejects.toThrow();
    });
    it.each([401, 404, 503])("does not substitute fixtures on HTTP %s", async (status) => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status })));
        await expect(getTransactions("account", "2026-06-01", "2026-06-17", new AbortController().signal)).rejects.toThrow();
    });
    it("preserves recorded case and original movement linkage", async () => {
        const linked = { ...record("refund"), originalTransactionId: "original", supportCaseId: "case-1", sourceKind: "dispute_effect" };
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(page([linked], 1)));
        const [transaction] = await getTransactions("account", "2026-06-01", "2026-06-17", new AbortController().signal);
        expect(transaction).toMatchObject({ originalTransactionId: "original", supportCaseId: "case-1", sourceKind: "dispute_effect" });
    });
    it("preserves owned country and nullable city without exposing fraud metadata", async () => {
        const located = { ...record("tx"), country: "CO", city: null, fraud_score: 0.2, is_fraud: true };
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(page([located], 1)));
        const [transaction] = await getTransactions("account", "2026-06-01", "2026-06-17", new AbortController().signal);
        expect(transaction).toMatchObject({ country: "CO", city: null });
        expect(transaction).not.toHaveProperty("fraud_score");
        expect(transaction).not.toHaveProperty("is_fraud");
    });
    it("returns a verified empty page", async () => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(page([], 0)));
        expect(await getTransactions("account", "2026-06-01", "2026-06-17", new AbortController().signal)).toEqual([]);
    });
    it("maps a transaction record to the persisted financial shape, scoped to the requested account", async () => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(page([{
            id: "tx-1", timestamp: "2026-06-05T10:00:00", amount: 42.5, currency: "USD",
            type: "purchase", category: "Retail", paymentType: "CreditCard",
            recipientName: "Contoso Store", status: "approved",
        }], 1)));
        const [transaction] = await getTransactions("account", "2026-06-01", "2026-06-17", new AbortController().signal);
        expect(transaction).toEqual({
            id: "tx-1", product_number: "account", date: "2026-06-05T10:00:00",
            amount: "42.5", currency: "USD", type: "purchase", category: "Retail",
            channel: "CreditCard", merchant: "Contoso Store", status: "approved",
        });
    });
    it.each(["opaque/one", "opaque-two"])("uses opaque card ID %s and masks the display number across pages", async (productId) => {
        const fetch = vi.fn().mockResolvedValueOnce(page([record("1")], 2)).mockResolvedValueOnce(page([record("2")], 2));
        vi.stubGlobal("fetch", fetch);
        const signal = new AbortController().signal;
        const transactions = await getTransactions("4111111111111234", "2026-06-01", "2026-06-17", signal, productId);
        expect(transactions.map((item) => item.product_number)).toEqual(["4111 **** **** 1234", "4111 **** **** 1234"]);
        for (const [url, options] of fetch.mock.calls) {
            expect(url).toContain(`/transactions/products/${encodeURIComponent(productId)}/history?`);
            expect(url).not.toContain("4111111111111234"); expect(options.signal).toBe(signal);
        }
        expect(fetch.mock.calls[1][0]).toContain("offset=1");
    });
    it.each([401, 404, 503])("fails closed for card HTTP %s", async (status) => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status })));
        await expect(getTransactions("**** 1234", "2026-06-01", "2026-06-17", new AbortController().signal, "opaque")).rejects.toThrow();
    });
    it("supports card empty history and cancellation", async () => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(page([], 0)).mockRejectedValueOnce(new DOMException("Aborted", "AbortError")));
        const signal = new AbortController().signal;
        expect(await getTransactions("", "2026-06-01", "2026-06-17", signal, "opaque")).toEqual([]);
        await expect(getTransactions("", "2026-06-01", "2026-06-17", signal, "opaque")).rejects.toMatchObject({ name: "AbortError" });
    });
    it("propagates request cancellation", async () => {
        vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("Aborted", "AbortError")));
        await expect(getTransactions("account", "2026-06-01", "2026-06-17", new AbortController().signal)).rejects.toMatchObject({ name: "AbortError" });
    });
});
