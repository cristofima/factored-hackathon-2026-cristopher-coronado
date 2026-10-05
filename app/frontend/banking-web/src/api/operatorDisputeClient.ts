import { getAuthToken } from "@/api/authToken";
import { ApiError, readApiError } from "@/api/errors";
import { z } from "zod";
import { effectsSchema, protectionSchema } from "@/api/supportCaseContracts";
export { effectsSchema, protectionSchema } from "@/api/supportCaseContracts";

const timestamp = z.string().datetime({ offset: true, local: true });
const version = z.number().int().min(0).safe();
const caseSchema = z.object({
    caseId: z.string().min(1),
    status: z.enum(["OPEN", "WAITING_USER_APPROVAL", "IN_REVIEW", "PENDING_EFFECTS", "RESOLVED_VALID", "RESOLVED_INVALID", "RESOLVED"]),
    triageOutcome: z.string().nullable(),
    openedAt: timestamp, updatedAt: timestamp, claimVersion: version,
});
const evidenceSchema = z.object({
    transactionId: z.string(), productId: z.string(), productType: z.string(), customerId: z.string(),
    amount: z.string(), currency: z.string(), transactionDate: timestamp, status: z.string(),
    fraudScore: z.string().nullable(), merchant: z.string().nullable(), country: z.string().nullable(),
    city: z.string().nullable(), responseCode: z.string().nullable(), isFraud: z.boolean().nullable(), sourceKind: z.string(),
});
const detailSchema = caseSchema.extend({
    caseVersion: version.optional(), evidenceVersion: version.optional(), evidence: evidenceSchema.nullable().optional(),
    verdict: z.enum(["valid", "invalid"]).nullable().optional(), rationale: z.string().nullable().optional(),
    eligibleDestinations: z.array(z.object({ productId: z.string(), productNumber: z.string().nullable(),
        productType: z.string(), currency: z.string().nullable() })).optional(),
    effects: effectsSchema.nullable().optional(), effectCode: z.string().nullable().optional(),
    cardProtection: protectionSchema.nullable().optional(), productProtectionStatus: z.string().nullable().optional(),
    customerName: z.string().nullable().optional(),
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

async function request<T>(schema: z.ZodType<T>, path: string, signal?: AbortSignal, method: "GET" | "POST" = "GET", body?: unknown): Promise<T> {
    signal?.throwIfAborted();
    const token = getAuthToken();
    if (!token) throw new ApiError("AUTH_REQUIRED");
    const response = await fetch(`${TRANSACTION_API_URL}/operator/support-cases${path}`, {
        method,
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        headers: { ...(body === undefined ? {} : { "Content-Type": "application/json" }), Authorization: `Bearer ${token}`, },
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

const rationaleSchema = z.string().trim().min(1).max(1000);
export const adjudicateRequestSchema = z.object({ verdict: z.enum(["valid", "invalid"]), rationale: rationaleSchema,
    expected_case_version: version, expected_evidence_version: version.min(1), destination_product_id: z.string().min(1).optional() });
export const retryEffectsRequestSchema = z.object({ expected_case_version: version, destination_product_id: z.string().min(1).optional() });
export const protectionRequestSchema = z.object({ expected_case_version: version, rationale: rationaleSchema, blocked: z.boolean() });
async function action<S extends z.ZodTypeAny>(caseId: string, suffix: string, schema: S, body: z.input<S>, signal?: AbortSignal): Promise<OperatorCaseDetail> {
    validateId(caseId);
    const parsed = schema.safeParse(body);
    if (!parsed.success) throw new ApiError("INVALID_REQUEST");
    return request(detailSchema, `/${encodeURIComponent(caseId)}/${suffix}`, signal, "POST", parsed.data);
}
export function adjudicateOperatorCase(caseId: string, body: z.input<typeof adjudicateRequestSchema>, signal?: AbortSignal): Promise<OperatorCaseDetail> {
    return action(caseId, "adjudicate", adjudicateRequestSchema, body, signal);
}
export function retryOperatorEffects(caseId: string, body: z.input<typeof retryEffectsRequestSchema>, signal?: AbortSignal): Promise<OperatorCaseDetail> {
    return action(caseId, "effects/retry", retryEffectsRequestSchema, body, signal);
}
export function protectOperatorCard(caseId: string, body: z.input<typeof protectionRequestSchema>, signal?: AbortSignal): Promise<OperatorCaseDetail> {
    return action(caseId, "card-protection", protectionRequestSchema, body, signal);
}
