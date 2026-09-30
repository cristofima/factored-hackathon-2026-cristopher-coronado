const errorCodes = [
    "AUTH_REQUIRED", "INVALID_CREDENTIALS", "ACCESS_DENIED", "ACCOUNT_UNAVAILABLE",
    "SERVICE_UNAVAILABLE", "INVALID_DATE_RANGE", "INVALID_REQUEST",
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
        case "INVALID_DATE_RANGE": return "Choose a valid inclusive start and end date.";
        default: return fallback;
    }
}