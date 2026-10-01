export interface SupportCase {
    caseId: string;
    productNumber: string | null;
    transactionId: string;
    reason: string;
    status: string;
    triageOutcome: string | null;
    resolutionOutcome: string | null;
    resolutionNotes: string | null;
    recommendationType: string | null;
    recommendationRationale: string | null;
    recommendationOptedOut: boolean;
    openedAt: string;
    updatedAt: string;
    resolvedAt: string | null;
}

export interface SupportCaseEvent {
    eventType: string;
    actor: string;
    message: string | null;
    createdAt: string;
}
