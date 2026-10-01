import { getAuthToken } from "@/api/authToken";
import { ApiError, readApiError } from "@/api/errors";
import type { SupportCase, SupportCaseEvent } from "@/models/SupportCase";

const TRANSACTION_API_URL = import.meta.env.VITE_TRANSACTION_API_URL || "";

function authHeaders(): HeadersInit {
    const token = getAuthToken();
    if (!token) throw new ApiError("AUTH_REQUIRED");
    return { Authorization: `Bearer ${token}` };
}

export async function listSupportCases(signal?: AbortSignal): Promise<SupportCase[]> {
    const response = await fetch(`${TRANSACTION_API_URL}/support-cases`, {
        headers: authHeaders(),
        signal,
    });
    if (!response.ok) throw await readApiError(response);
    return response.json();
}

export async function getSupportCase(caseId: string, signal?: AbortSignal): Promise<SupportCase> {
    const response = await fetch(`${TRANSACTION_API_URL}/support-cases/${encodeURIComponent(caseId)}`, {
        headers: authHeaders(),
        signal,
    });
    if (!response.ok) throw await readApiError(response);
    return response.json();
}

export async function getSupportCaseTimeline(
    caseId: string, signal?: AbortSignal,
): Promise<SupportCaseEvent[]> {
    const response = await fetch(
        `${TRANSACTION_API_URL}/support-cases/${encodeURIComponent(caseId)}/timeline`,
        { headers: authHeaders(), signal },
    );
    if (!response.ok) throw await readApiError(response);
    return response.json();
}

export async function openSupportCase(
    transactionId: string, reason: string, signal?: AbortSignal,
): Promise<SupportCase> {
    const response = await fetch(`${TRANSACTION_API_URL}/support-cases`, {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ transactionId, reason }),
        signal,
    });
    if (!response.ok) throw await readApiError(response);
    return response.json();
}

export async function respondToSupportCaseApproval(
    caseId: string, approved: boolean, signal?: AbortSignal,
): Promise<SupportCase> {
    const response = await fetch(
        `${TRANSACTION_API_URL}/support-cases/${encodeURIComponent(caseId)}/approval`,
        {
            method: "POST",
            headers: { ...authHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({ approved }),
            signal,
        },
    );
    if (!response.ok) throw await readApiError(response);
    return response.json();
}

export async function dismissSupportCaseRecommendation(
    caseId: string, signal?: AbortSignal,
): Promise<SupportCase> {
    const response = await fetch(
        `${TRANSACTION_API_URL}/support-cases/${encodeURIComponent(caseId)}/recommendation/dismiss`,
        { method: "POST", headers: authHeaders(), signal },
    );
    if (!response.ok) throw await readApiError(response);
    return response.json();
}
