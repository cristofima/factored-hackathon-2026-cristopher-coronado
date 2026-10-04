import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { MessageSquareWarning } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { listSupportCases, openSupportCase } from "@/api/disputeClient";
import { activeTransactionCases } from "@/hooks/useDisputeEligibility";
import { ApiError, errorTranslationKey } from "@/api/errors";

export default function ReportDisputeDialog({
  transactionId,
  onCasesChanged,
}: Readonly<{ transactionId: string; onCasesChanged: () => void }>) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submitting = useRef(false);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);

  const submit = async () => {
    const submittedReason = reason.trim();
    if (!submittedReason || submitting.current) return;
    submitting.current = true;
    setPending(true);
    setError(null);
    const controller = new AbortController();
    request.current = controller;
    try {
      const cases = await listSupportCases(controller.signal);
      controller.signal.throwIfAborted();
      const existing = activeTransactionCases(cases).get(transactionId);
      let created = existing;
      if (!created) {
        try {
          created = await openSupportCase(transactionId, submittedReason, controller.signal);
        } catch (cause) {
          if (!(cause instanceof ApiError) || cause.code !== "DISPUTE_ALREADY_ACTIVE") throw cause;
          const currentCases = await listSupportCases(controller.signal).catch(() => { throw cause; });
          controller.signal.throwIfAborted();
          created = activeTransactionCases(currentCases).get(transactionId);
          if (!created) throw cause;
        }
      }
      controller.signal.throwIfAborted();
      setOpen(false);
      setReason("");
      onCasesChanged();
      navigate(`/support-cases/${created.caseId}`);
    } catch (cause) {
      if (!controller.signal.aborted) {
        setError(errorTranslationKey(cause, "Could not open the dispute"));
      }
    } finally {
      if (!controller.signal.aborted) {
        submitting.current = false;
        setPending(false);
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => { if (!submitting.current) setOpen(nextOpen); }}>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="border-sky-300 bg-sky-50 text-sky-800 hover:border-sky-400 hover:bg-sky-100 hover:text-sky-900 focus-visible:ring-sky-600"
        >
          <MessageSquareWarning aria-hidden="true" />
          {t("Report dispute")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("Report a transaction dispute")}</DialogTitle>
        </DialogHeader>
        <Textarea
          disabled={pending}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder={t("Describe why you don't recognize this charge") ?? ""}
          rows={4}
        />
        {error && <div role="alert">{t(error)}</div>}
        <DialogFooter>
          <Button disabled={pending || !reason.trim()} onClick={submit}>
            {t("Submit dispute")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
