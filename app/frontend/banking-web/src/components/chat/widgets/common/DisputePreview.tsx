import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { DisputePreviewConsent } from "@/components/DisputePreviewConsent";
import { disputePreviewSchema } from "@/api/supportCaseContracts";
import { Button } from "@/components/ui/button";
import { useChat } from "../../ResponsesChatProvider";
import type { ClientWidgetProps } from "../WidgetRegistry";
import { visibleConversation } from "../../sessionHistory";

export function DisputePreview({ args, itemId }: ClientWidgetProps) {
  const { t } = useTranslation();
  const { activeThreadId, items, isStreaming, sendWidgetAction, isThreadLocked } = useChat();
  const locked = Boolean(activeThreadId && isThreadLocked(activeThreadId));
  const originalThread = useRef(activeThreadId);
  const [continuation, setContinuation] = useState<{ threadId: string; caseId: string | null; declined: boolean } | null>(null);
  const [failed, setFailed] = useState(false);
  const preview = disputePreviewSchema.safeParse(args.preview);
  async function continueChat(value: NonNullable<typeof continuation>) {
    setContinuation(value);
    setFailed(false);
    try {
      const outcome = await sendWidgetAction(value.threadId, itemId, {
        type: "dispute_preview_decision", payload: { caseId: value.caseId, declined: value.declined },
      });
      setFailed(outcome !== "success");
    } catch { setFailed(true); }
  }
  if (!preview.success && args.recordedDecision) return <p>{t("Dispute decision recorded")}</p>;
  if (!preview.success) return <p>{t("Dispute preview unavailable")}</p>;
  return <>
    <DisputePreviewConsent preview={preview.data} conversationHistory={visibleConversation(items)} disabled={locked || isStreaming || !activeThreadId || activeThreadId !== originalThread.current}
      onAccepted={(supportCase) => { if (originalThread.current) void continueChat({ threadId: originalThread.current, caseId: supportCase.caseId, declined: false }); }}
            onDeclined={() => { if (originalThread.current) void continueChat({ threadId: originalThread.current, caseId: null, declined: true }); }} />
    {failed && continuation && <div role="alert"><p>{t("Dispute chat continuation unavailable")}</p>
      <Button disabled={locked || isStreaming || activeThreadId !== continuation.threadId} onClick={() => void continueChat(continuation)}>{t("Retry chat continuation")}</Button></div>}
  </>;
}
