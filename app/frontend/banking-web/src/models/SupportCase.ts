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
    financialEffectsStatus?: string;
    cardProtectionStatus?: string;
}

export interface SupportCaseEvent {
    eventType: string;
    actor: string;
    message: string | null;
    displayMessage?: string | null;
    createdAt: string;
}

export function supportCaseEventMessageKey(event: SupportCaseEvent): string {
    if (event.eventType === "RESOLVED") {
        if (event.message === "Provisional credit issued; case resolved without manual review") {
            return "support-cases.messages.PROVISIONAL_CREDIT";
        }
        if (event.message === "Case closed: withdrawn by customer") {
            return "support-cases.messages.WITHDRAWN";
        }
        return "support-cases.messages.CUSTOM_NOTE";
    }
    if (event.eventType === "ESCALATED_TO_REVIEW" &&
        event.message?.startsWith("No fraud score available for this transaction;")) {
        return "support-cases.messages.INSUFFICIENT_SIGNAL";
    }
    return `support-cases.messages.${event.eventType}`;
}
