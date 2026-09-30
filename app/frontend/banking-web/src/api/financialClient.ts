import { getAuthToken } from "@/api/authToken";
import { ApiError, readApiError } from "@/api/errors";

export interface FinancialTransaction {
    id: string;
    product_number: string;
    date: string;
    amount: string;
    currency: string;
    type: string | null;
    category: string | null;
    channel: string | null;
    merchant: string | null;
    status: string | null;
}

interface TransactionPage {
    items: FinancialTransaction[];
    total: number;
}

const BFF_URL = import.meta.env.VITE_RESPONSES_BFF_URL || "";

export async function getTransactions(
    accountId: string, start: string, end: string, signal: AbortSignal,
): Promise<FinancialTransaction[]> {
    const token = getAuthToken();
    if (!token) throw new ApiError("AUTH_REQUIRED");
    const records: FinancialTransaction[] = [];
    const ids = new Set<string>();
    let expectedTotal: number | undefined;
    while (true) {
        const query = new URLSearchParams({ start_date: start, end_date: end, limit: "100", offset: String(records.length) });
        const response = await fetch(`${BFF_URL}/accounts/${encodeURIComponent(accountId)}/transactions?${query}`, {
            headers: { Authorization: `Bearer ${token}` }, signal,
        });
        if (!response.ok) {
            throw await readApiError(response);
        }
        const page: TransactionPage = await response.json();
        if (expectedTotal !== undefined && expectedTotal !== page.total) {
            throw new ApiError("SERVICE_UNAVAILABLE");
        }
        expectedTotal = page.total;
        for (const record of page.items) {
            if (record.product_number !== accountId || ids.has(record.id)) {
                throw new ApiError("SERVICE_UNAVAILABLE");
            }
            ids.add(record.id);
        }
        records.push(...page.items);
        if (records.length === expectedTotal) return records;
        if (!page.items.length || records.length > expectedTotal) {
            throw new ApiError("SERVICE_UNAVAILABLE");
        }
    }
}