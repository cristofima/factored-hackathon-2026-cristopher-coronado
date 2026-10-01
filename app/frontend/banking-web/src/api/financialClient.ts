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

interface TransactionRecord {
    id: string;
    timestamp: string | null;
    amount: number | null;
    currency: string | null;
    type: string | null;
    category: string | null;
    paymentType: string | null;
    recipientName: string | null;
    status: string | null;
}

interface TransactionPage {
    items: TransactionRecord[];
    total: number;
}

const TRANSACTION_API_URL = import.meta.env.VITE_TRANSACTION_API_URL || "";

const mapRecord = (record: TransactionRecord, accountId: string): FinancialTransaction => ({
    id: record.id,
    product_number: accountId,
    date: record.timestamp ?? "",
    amount: record.amount !== null ? String(record.amount) : "",
    currency: record.currency ?? "",
    type: record.type,
    category: record.category,
    channel: record.paymentType,
    merchant: record.recipientName,
    status: record.status,
});

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
        const response = await fetch(
            `${TRANSACTION_API_URL}/transactions/${encodeURIComponent(accountId)}/history?${query}`,
            { headers: { Authorization: `Bearer ${token}` }, signal },
        );
        if (!response.ok) {
            throw await readApiError(response);
        }
        const page: TransactionPage = await response.json();
        if (expectedTotal !== undefined && expectedTotal !== page.total) {
            throw new ApiError("SERVICE_UNAVAILABLE");
        }
        expectedTotal = page.total;
        const mapped = page.items.map((record) => mapRecord(record, accountId));
        for (const record of mapped) {
            if (ids.has(record.id)) {
                throw new ApiError("SERVICE_UNAVAILABLE");
            }
            ids.add(record.id);
        }
        records.push(...mapped);
        if (records.length === expectedTotal) return records;
        if (!mapped.length || records.length > expectedTotal) {
            throw new ApiError("SERVICE_UNAVAILABLE");
        }
    }
}
