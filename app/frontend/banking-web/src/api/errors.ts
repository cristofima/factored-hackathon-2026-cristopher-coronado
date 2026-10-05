const errorCodes = [
    "AUTH_REQUIRED", "INVALID_CREDENTIALS", "ACCESS_DENIED", "ACCOUNT_UNAVAILABLE",
    "DISPUTE_PREVIEW_INVALID", "DISPUTE_PREVIEW_EXPIRED", "DISPUTE_PREVIEW_STALE", "DISPUTE_UNAVAILABLE", "DISPUTE_INELIGIBLE",
    "SERVICE_UNAVAILABLE", "INVALID_DATE_RANGE", "INVALID_REQUEST", "DISPUTE_ALREADY_ACTIVE", "DISPUTE_CARD_ONLY", "OPERATOR_CLAIM_CONFLICT", "CASE_NOT_FOUND", "CASE_VERSION_CONFLICT", "EVIDENCE_VERSION_CONFLICT", "EVIDENCE_UNAVAILABLE", "EVIDENCE_CHANGED", "DESTINATION_NOT_ELIGIBLE", "CASE_NOT_IN_REVIEW", "CASE_NOT_PENDING_EFFECTS", "OPERATOR_NOT_ASSIGNED", "CREDIT_ALREADY_APPLIED", "CASE_VERDICT_CONFLICT", "CARD_PROTECTION_NOT_ELIGIBLE", "EFFECT_EXECUTION_FAILED", "DESTINATION_REQUIRED", "DESTINATION_UNAVAILABLE",
] as const;

export type ApiErrorCode = typeof errorCodes[number];

export class ApiError extends Error {
    constructor(public readonly code: ApiErrorCode) {
        super(code);
        this.name = "ApiError";
    }
}

export async function readApiError(response: Response): Promise<ApiError> {
    const body = await response.json().catch(() => null);
    const code: unknown = body?.detail?.code;
    if (typeof code === "string" && (errorCodes as readonly string[]).includes(code)) {
        return new ApiError(code as ApiErrorCode);
    }
    if (response.status === 401) return new ApiError("AUTH_REQUIRED");
    if (response.status === 403) return new ApiError("ACCESS_DENIED");
    return new ApiError("SERVICE_UNAVAILABLE");
}

export function errorTranslationKey(error: unknown, fallback: string): string {
    if (!(error instanceof ApiError)) return fallback;
    switch (error.code) {
        case "AUTH_REQUIRED": return "Session expired";
        case "ACCESS_DENIED": return "Access denied";
        case "DISPUTE_ALREADY_ACTIVE": return "An active dispute already exists. Retry to open the existing case.";
        case "DISPUTE_CARD_ONLY": return "Only debit or credit card transactions can be disputed.";
        case "DISPUTE_PREVIEW_EXPIRED": return "Dispute preview expired";
        case "DISPUTE_PREVIEW_INVALID":
        case "DISPUTE_PREVIEW_STALE":
        case "DISPUTE_UNAVAILABLE":
        case "DISPUTE_INELIGIBLE": return "Dispute preview unavailable";
        case "OPERATOR_CLAIM_CONFLICT": return "Case changed or already assigned. Refresh and try again.";
        case "CASE_VERDICT_CONFLICT":
        case "CASE_VERSION_CONFLICT":
        case "EVIDENCE_VERSION_CONFLICT":
        case "EVIDENCE_CHANGED": return "Case or evidence changed. Refresh before acting.";
        case "DESTINATION_NOT_ELIGIBLE": return "Destination is no longer eligible. Refresh before acting.";
        case "EVIDENCE_UNAVAILABLE": return "Verified evidence is unavailable. No financial completion is confirmed.";
        case "INVALID_DATE_RANGE": return "Choose a valid inclusive start and end date.";
        default: return fallback;
    }
}