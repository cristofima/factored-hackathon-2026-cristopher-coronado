import type { z } from "zod";
import type { supportCaseSchema, supportCaseEventSchema } from "@/api/supportCaseContracts";

export type SupportCase = z.infer<typeof supportCaseSchema>;
export type SupportCaseEvent = z.infer<typeof supportCaseEventSchema>;

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
