import { afterEach, describe, expect, it, vi } from "vitest";
import { getTransactions } from "./financialClient";

vi.mock("./authToken", () => ({ getAuthToken: () => "test-only-token" }));

const record = (id: string, product_number = "account") => ({ id, product_number, amount: "1.0000" });
const page = (items: ReturnType<typeof record>[], total: number) => new Response(JSON.stringify({ items, total }));

afterEach(() => vi.unstubAllGlobals());

describe("BFF transaction pagination", () => {
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
        [page([record("1", "foreign")], 1)],
        [page([], 1)],
    ])("rejects inconsistent or foreign pages", async (...pages) => {
        const fetch = vi.fn();
        for (const response of pages) fetch.mockResolvedValueOnce(response);
        vi.stubGlobal("fetch", fetch);
        await expect(getTransactions("account", "2026-06-01", "2026-06-17", new AbortController().signal)).rejects.toThrow();
    });
    it.each([401, 404, 503])("does not substitute fixtures on HTTP %s", async (status) => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status })));
        await expect(getTransactions("account", "2026-06-01", "2026-06-17", new AbortController().signal)).rejects.toThrow();
    });
    it("returns a verified empty page", async () => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(page([], 0)));
        expect(await getTransactions("account", "2026-06-01", "2026-06-17", new AbortController().signal)).toEqual([]);
    });
    it("propagates request cancellation", async () => {
        vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("Aborted", "AbortError")));
        await expect(getTransactions("account", "2026-06-01", "2026-06-17", new AbortController().signal)).rejects.toMatchObject({ name: "AbortError" });
    });
});