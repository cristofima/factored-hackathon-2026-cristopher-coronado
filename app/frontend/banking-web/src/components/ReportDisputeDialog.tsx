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
import { listSupportCases, previewSupportCase } from "@/api/disputeClient";
import type { DisputePreview } from "@/api/supportCaseContracts";
import { DisputePreviewConsent } from "@/components/DisputePreviewConsent";
import { useAuth } from "@/context/AuthContext";
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
  const { user, sessionKey, logout } = useAuth();
  const scope = JSON.stringify([transactionId, user?.id, user?.identityVersion, sessionKey]);
  const latestScope = useRef(scope);
  latestScope.current = scope;
  const [proposal, setProposal] = useState<{ scope: string; preview: DisputePreview } | null>(null);
  useEffect(() => {
    setProposal(null); setOpen(false); setReason(""); setError(null);
    submitting.current = false; setPending(false);
    return () => request.current?.abort();
  }, [scope]);

  const submit = async () => {
    const submittedReason = reason.trim();
    if (!user || !submittedReason || submitting.current) return;
    submitting.current = true;
    setPending(true);
    setError(null);
    const controller = new AbortController();
    request.current = controller;
    try {
      const cases = await listSupportCases(controller.signal);
      controller.signal.throwIfAborted();
      const existing = activeTransactionCases(cases).get(transactionId);
      if (latestScope.current !== scope) return;
      if (existing) {
        setOpen(false);
        setReason("");
        onCasesChanged();
        navigate(`/support-cases/${existing.caseId}`);
        return;
      }
      try {
        const preview = await previewSupportCase(transactionId, submittedReason, controller.signal);
        if (!controller.signal.aborted && latestScope.current === scope) setProposal({ scope, preview });
      } catch (cause) {
        if (!(cause instanceof ApiError) || cause.code !== "DISPUTE_ALREADY_ACTIVE") throw cause;
        const currentCases = await listSupportCases(controller.signal).catch((reloadError) => {
          if (controller.signal.aborted || (reloadError instanceof ApiError && ["AUTH_REQUIRED", "AUTH_EXPIRED", "AUTH_INVALID", "ACCESS_DENIED"].includes(reloadError.code))) throw reloadError;
          throw cause;
        });
        controller.signal.throwIfAborted();
        if (latestScope.current !== scope) return;
        const active = activeTransactionCases(currentCases).get(transactionId);
        if (!active) throw cause;
        setOpen(false); onCasesChanged(); navigate(`/support-cases/${active.caseId}`);
      }
    } catch (cause) {
      if (!controller.signal.aborted && latestScope.current === scope) {
        if (cause instanceof ApiError && ["AUTH_REQUIRED", "AUTH_EXPIRED", "AUTH_INVALID"].includes(cause.code)) logout();
        setError(errorTranslationKey(cause, "Could not open the dispute"));
      }
    } finally {
      if (!controller.signal.aborted && latestScope.current === scope) {
        submitting.current = false;
        setPending(false);
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => {
      setOpen(nextOpen);
      if (!nextOpen) { request.current?.abort(); submitting.current = false; setPending(false); setProposal(null); setError(null); }
    }}>
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
        {open && proposal?.scope === scope ? <DisputePreviewConsent key={proposal.preview.previewToken} preview={proposal.preview}
          onAccepted={(supportCase) => {
            setOpen(false); setProposal(null); setReason(""); onCasesChanged(); navigate(`/support-cases/${supportCase.caseId}`);
          }} onDeclined={() => { setOpen(false); setProposal(null); setReason(""); }} /> : <>
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
            {t("Preview dispute")}
          </Button>
        </DialogFooter>
        </>}
      </DialogContent>
    </Dialog>
  );
}
