import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { DisputePreviewConsent } from "@/components/DisputePreviewConsent";
import { disputePreviewSchema } from "@/api/supportCaseContracts";
import { Button } from "@/components/ui/button";
import { useChat } from "../../ResponsesChatProvider";
import type { ClientWidgetProps } from "../WidgetRegistry";

export function DisputePreview({ args, itemId }: ClientWidgetProps) {
  const { t } = useTranslation();
  const { activeThreadId, isStreaming, sendWidgetAction } = useChat();
  const originalThread = useRef(activeThreadId);
  const latestThread = useRef(activeThreadId);
  latestThread.current = activeThreadId;
  const [continuation, setContinuation] = useState<{ threadId: string; caseId: string | null; declined: boolean } | null>(null);
  const [failed, setFailed] = useState(false);
  const preview = disputePreviewSchema.safeParse(args.preview);
  async function continueChat(value: NonNullable<typeof continuation>) {
    setContinuation(value);
    if (latestThread.current !== value.threadId) { setFailed(true); return; }
    setFailed(false);
    try {
      const outcome = await sendWidgetAction(value.threadId, itemId, {
        type: "dispute_preview_decision", payload: { caseId: value.caseId, declined: value.declined },
      });
      setFailed(outcome !== "success");
    } catch { setFailed(true); }
  }
  if (!preview.success) return <p>{t("Dispute preview unavailable")}</p>;
  return <>
    <DisputePreviewConsent preview={preview.data} disabled={isStreaming || !activeThreadId || activeThreadId !== originalThread.current}
      onAccepted={(supportCase) => { if (originalThread.current) void continueChat({ threadId: originalThread.current, caseId: supportCase.caseId, declined: false }); }}
            onDeclined={() => { if (originalThread.current) void continueChat({ threadId: originalThread.current, caseId: null, declined: true }); }} />
    {failed && continuation && <div role="alert"><p>{t("Dispute chat continuation unavailable")}</p>
      <Button disabled={isStreaming || activeThreadId !== continuation.threadId} onClick={() => void continueChat(continuation)}>{t("Retry chat continuation")}</Button></div>}
  </>;
}
