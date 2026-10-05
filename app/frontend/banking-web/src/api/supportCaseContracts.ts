import { z } from "zod";

const timestamp = z.string().datetime({ offset: true, local: true });
export const effectsSchema = z.object({
  movementId: z.string().min(1), destinationProductId: z.string().min(1),
  amount: z.string().regex(/^\d+(\.\d+)?$/), currency: z.string().min(1),
  balanceDelta: z.string().regex(/^-?\d+(\.\d+)?$/), executedAt: timestamp,
});
export const protectionSchema = z.object({
  blocked: z.boolean(), priorStatus: z.string().nullable(), rationale: z.string(), caseId: z.string(),
  updatedAt: timestamp, scope: z.literal("LOCAL_PRODUCT_ONLY"),
});

export const supportCaseStatusSchema = z.enum([
  "OPEN", "WAITING_USER_APPROVAL", "IN_REVIEW", "PENDING_EFFECTS",
  "RESOLVED_VALID", "RESOLVED_INVALID", "RESOLVED",
]);
export const supportCaseEventSchema = z.object({
  eventType: z.string(), actor: z.string(), message: z.string().nullable(),
  displayMessage: z.string().nullable().optional(), createdAt: z.string(),
});
export const supportCaseSchema = z.object({
  caseId: z.string().min(1), productNumber: z.string().nullable(),
  transactionId: z.string().min(1), reason: z.string(), status: supportCaseStatusSchema,
  triageOutcome: z.string().nullable(), resolutionOutcome: z.string().nullable(),
  resolutionNotes: z.string().nullable(), recommendationType: z.string().nullable(),
  recommendationRationale: z.string().nullable(), recommendationOptedOut: z.boolean(),
  openedAt: z.string(), updatedAt: z.string(), resolvedAt: z.string().nullable(),
  financialEffectsStatus: z.string().optional(), cardProtectionStatus: z.string().optional(),
  caseVersion: z.number().int().min(0).safe().optional(),
  verdict: z.enum(["valid", "invalid"]).nullable().optional(), rationale: z.string().nullable().optional(),
  effectCode: z.string().nullable().optional(), effects: effectsSchema.nullable().optional(),
  cardProtection: protectionSchema.nullable().optional(),
});

export const disputePreviewSchema = z.object({
  previewToken: z.string().min(1), transactionId: z.string().min(1), reason: z.string().min(1),
  expiresAt: timestamp,
  transaction: z.object({
    id: z.string().min(1), description: z.string().nullable().optional(),
    recipientName: z.string().nullable().optional(),
    amount: z.number().finite().nullable().optional(), currency: z.string().nullable().optional(),
    timestamp: z.string().nullable().optional(), product_number: z.string().nullable().optional(),
    country: z.string().nullable().optional(), city: z.string().nullable().optional(),
    status: z.string().nullable().optional(),
  }),
}).refine(preview => preview.transactionId === preview.transaction.id);

export type DisputePreview = z.infer<typeof disputePreviewSchema>;

export const conversationMessageSchema = z.object({
  role: z.enum(["user", "assistant"]), text: z.string().min(1).max(100000),
});
export const caseConversationSchema = z.object({
  source: z.literal("CUSTOMER_PROVIDED"),
  messages: z.array(conversationMessageSchema).max(100),
}).refine(history => history.messages.reduce((size, message) => size + message.text.length, 0) <= 100000);
export type ConversationMessage = z.infer<typeof conversationMessageSchema>;
export type CaseConversation = z.infer<typeof caseConversationSchema>;

export function isTerminalCase(status: string): boolean {
  return ["RESOLVED", "RESOLVED_VALID", "RESOLVED_INVALID"].includes(status);
}
