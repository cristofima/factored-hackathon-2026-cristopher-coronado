import { getAuthToken } from "@/api/authToken";
import { ApiError, readApiError } from "@/api/errors";
import { z } from "zod";

const timestamp = z.string().datetime({ offset: true, local: true });
const version = z.number().int().min(0).safe();
const caseSchema = z.object({
    caseId: z.string().min(1),
    status: z.enum(["OPEN", "WAITING_USER_APPROVAL", "IN_REVIEW", "RESOLVED"]),
    triageOutcome: z.string().nullable(),
    openedAt: timestamp, updatedAt: timestamp, claimVersion: version,
});
const detailSchema = caseSchema.extend({
    assignedOperatorSub: z.string().min(1), claimedAt: timestamp,
    reason: z.string(), transactionId: z.string().min(1), productId: z.string().min(1),
    events: z.array(z.object({
        eventId: z.string().min(1), eventType: z.string(), actor: z.string(),
        message: z.string().nullable(), createdAt: timestamp,
        operatorSub: z.string().nullable(), operatorIdentityVersion: version.nullable(),
        claimVersion: version.nullable(),
    })),
});
const queueSchema = z.object({
    items: z.array(caseSchema), total: version, offset: version,
    limit: z.number().int().min(1).max(100),
});

function validateId(caseId: string): void {
    if (!caseId.trim() || [".", ".."].includes(caseId)) throw new ApiError("INVALID_REQUEST");
}

const TRANSACTION_API_URL = import.meta.env.VITE_TRANSACTION_API_URL || "";

export type OperatorSupportCase = z.infer<typeof caseSchema>;
export type OperatorCaseDetail = z.infer<typeof detailSchema>;
export type OperatorCaseQueue = z.infer<typeof queueSchema>;

async function request<T>(schema: z.ZodType<T>, path: string, signal?: AbortSignal, method: "GET" | "POST" = "GET"): Promise<T> {
    signal?.throwIfAborted();
    const token = getAuthToken();
    if (!token) throw new ApiError("AUTH_REQUIRED");
    const response = await fetch(`${TRANSACTION_API_URL}/operator/support-cases${path}`, {
        method,
        headers: { Authorization: `Bearer ${token}`, },
            signal,
    });
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

export type OperatorCaseView = "available" | "assigned";

export async function listOperatorCases(signal?: AbortSignal, offset = 0, limit = 50, view: OperatorCaseView = "available"): Promise<OperatorCaseQueue> {
    if (!Number.isSafeInteger(offset) || offset < 0 || !Number.isInteger(limit) || limit < 1 || limit > 100 || !["available", "assigned"].includes(view)) {
        throw new ApiError("INVALID_REQUEST");
    }
    return request(queueSchema, `?offset=${offset}&limit=${limit}&view=${view}`, signal);
}

export async function getOperatorCase(caseId: string, signal?: AbortSignal): Promise<OperatorCaseDetail> {
    validateId(caseId);
    return request(detailSchema, `/${encodeURIComponent(caseId)}`, signal);
}

export async function claimOperatorCase(caseId: string, signal?: AbortSignal): Promise<OperatorCaseDetail> {
    validateId(caseId);
    return request(detailSchema, `/${encodeURIComponent(caseId)}/claim`, signal, "POST");
}
