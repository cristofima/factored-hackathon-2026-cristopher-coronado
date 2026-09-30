import { getAuthToken } from "@/api/authToken";

export interface FinancialTransaction {
    id: string;
    account_id: string;
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
    if (!token) throw new Error("Sign in to view transactions");
    const records: FinancialTransaction[] = [];
    const ids = new Set<string>();
    let expectedTotal: number | undefined;
    while (true) {
        const query = new URLSearchParams({ start_date: start, end_date: end, limit: "100", offset: String(records.length) });
        const response = await fetch(`${BFF_URL}/accounts/${encodeURIComponent(accountId)}/transactions?${query}`, {
            headers: { Authorization: `Bearer ${token}` }, signal,
        });
        if (!response.ok) {
            throw new Error(response.status === 401 ? "Your session has expired. Sign in again."
                : response.status === 404 ? "Account is unavailable" : "Transactions are temporarily unavailable");
        }
        const page: TransactionPage = await response.json();
        if (expectedTotal !== undefined && expectedTotal !== page.total) {
            throw new Error("Transactions changed during loading. Retry to refresh the complete window.");
        }
        expectedTotal = page.total;
        for (const record of page.items) {
            if (record.account_id !== accountId || ids.has(record.id)) {
                throw new Error("Transaction pagination is inconsistent. Retry.");
            }
            ids.add(record.id);
        }
        records.push(...page.items);
        if (records.length === expectedTotal) return records;
        if (!page.items.length || records.length > expectedTotal) {
            throw new Error("The complete transaction window could not be loaded. Retry.");
        }
    }
}