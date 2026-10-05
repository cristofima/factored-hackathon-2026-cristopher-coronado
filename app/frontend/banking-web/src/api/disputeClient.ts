import { getAuthToken } from "@/api/authToken";
import { ApiError, readApiError } from "@/api/errors";
import { z } from "zod";
import { supportCaseSchema, supportCaseEventSchema, disputePreviewSchema, caseConversationSchema, type CaseConversation, type ConversationMessage, type DisputePreview } from "@/api/supportCaseContracts";
import type { SupportCase, SupportCaseEvent } from "@/models/SupportCase";

const TRANSACTION_API_URL = import.meta.env.VITE_TRANSACTION_API_URL || "";

async function decode<T>(response: Response, schema: z.ZodType<T>, signal?: AbortSignal): Promise<T> {
    signal?.throwIfAborted();
    if (!response.ok) {
        const error = await readApiError(response);
        signal?.throwIfAborted();
        throw error;
    }
    const payload = await response.json().catch(() => {
        signal?.throwIfAborted();
        throw new ApiError("SERVICE_UNAVAILABLE");
    });
    signal?.throwIfAborted();
    const parsed = schema.safeParse(payload);
    if (!parsed.success) throw new ApiError("SERVICE_UNAVAILABLE");
    return parsed.data;
}

function authHeaders(): HeadersInit {
    const token = getAuthToken();
    if (!token) throw new ApiError("AUTH_REQUIRED");
    return { Authorization: `Bearer ${token}` };
}

export async function listSupportCases(signal?: AbortSignal): Promise<SupportCase[]> {
    signal?.throwIfAborted();
    const response = await fetch(`${TRANSACTION_API_URL}/support-cases`, {
        headers: authHeaders(),
        signal,
    });
    return decode(response, z.array(supportCaseSchema), signal);
}

export async function getSupportCase(caseId: string, signal?: AbortSignal): Promise<SupportCase> {
    signal?.throwIfAborted();
    const response = await fetch(`${TRANSACTION_API_URL}/support-cases/${encodeURIComponent(caseId)}`, {
        headers: authHeaders(),
        signal,
    });
    return decode(response, supportCaseSchema, signal);
}

export async function getSupportCaseTimeline(
    caseId: string, signal?: AbortSignal,
): Promise<SupportCaseEvent[]> {
    signal?.throwIfAborted();
    const response = await fetch(
        `${TRANSACTION_API_URL}/support-cases/${encodeURIComponent(caseId)}/timeline`,
        { headers: authHeaders(), signal },
    );
    return decode(response, z.array(supportCaseEventSchema), signal);
}

export async function getSupportCaseDetail(
    caseId: string, signal?: AbortSignal,
): Promise<[SupportCase, SupportCaseEvent[]]> {
    const [supportCase, timeline] = await Promise.allSettled([
        getSupportCase(caseId, signal),
        getSupportCaseTimeline(caseId, signal),
    ]);
    if (supportCase.status === "rejected") throw supportCase.reason;
    if (timeline.status === "rejected") throw timeline.reason;
    return [supportCase.value, timeline.value];
}

export async function previewSupportCase(
    transactionId: string, reason: string, signal?: AbortSignal,
): Promise<DisputePreview> {
    signal?.throwIfAborted();
    const response = await fetch(`${TRANSACTION_API_URL}/support-cases/preview`, {
        method: "POST", headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ transactionId, reason }), signal,
    });
    const preview = await decode(response, disputePreviewSchema, signal);
    if (preview.transactionId !== transactionId || preview.reason !== reason) throw new ApiError("SERVICE_UNAVAILABLE");
    return preview;
}

export async function getCaseConversation(caseId: string, signal?: AbortSignal): Promise<CaseConversation> {
    signal?.throwIfAborted();
    const response = await fetch(`${TRANSACTION_API_URL}/support-cases/${encodeURIComponent(caseId)}/conversation`, {
        headers: authHeaders(), signal,
    });
    return decode(response, caseConversationSchema, signal);
}

export async function openSupportCase(previewToken: string, signal?: AbortSignal, conversationHistory?: ConversationMessage[]): Promise<SupportCase> {
    signal?.throwIfAborted();
    if (conversationHistory !== undefined && !caseConversationSchema.safeParse({ source: "CUSTOMER_PROVIDED", messages: conversationHistory }).success) {
        throw new ApiError("INVALID_REQUEST");
    }
    const response = await fetch(`${TRANSACTION_API_URL}/support-cases`, {
        method: "POST", headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ previewToken, ...(conversationHistory === undefined ? {} : { conversationHistory }) }), signal,
    });
    return decode(response, supportCaseSchema, signal);
}

export async function recoverSupportCase(previewToken: string, signal?: AbortSignal): Promise<SupportCase | null> {
    signal?.throwIfAborted();
    const response = await fetch(`${TRANSACTION_API_URL}/support-cases/recovery`, {
        method: "POST", headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ previewToken }), signal,
    });
    return decode(response, supportCaseSchema.nullable(), signal);
}

export async function respondToSupportCaseApproval(
    caseId: string, approved: boolean, signal?: AbortSignal,
): Promise<SupportCase> {
    signal?.throwIfAborted();
    const response = await fetch(
        `${TRANSACTION_API_URL}/support-cases/${encodeURIComponent(caseId)}/approval`,
        {
            method: "POST",
            headers: { ...authHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({ approved }),
            signal,
        },
    );
    return decode(response, supportCaseSchema, signal);
}

export async function dismissSupportCaseRecommendation(
    caseId: string, signal?: AbortSignal,
): Promise<SupportCase> {
    signal?.throwIfAborted();
    const response = await fetch(
        `${TRANSACTION_API_URL}/support-cases/${encodeURIComponent(caseId)}/recommendation/dismiss`,
        { method: "POST", headers: authHeaders(), signal },
    );
    return decode(response, supportCaseSchema, signal);
}
