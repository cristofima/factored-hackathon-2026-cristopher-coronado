import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
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
import { openSupportCase } from "@/api/disputeClient";
import { errorTranslationKey } from "@/api/errors";

export default function ReportDisputeDialog({
  transactionId,
}: Readonly<{ transactionId: string }>) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!reason.trim()) return;
    setPending(true);
    setError(null);
    try {
      const created = await openSupportCase(transactionId, reason.trim());
      setOpen(false);
      setReason("");
      navigate(`/support-cases/${created.caseId}`);
    } catch (cause) {
      setError(errorTranslationKey(cause, "Could not open the dispute"));
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          {t("Report dispute")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("Report a transaction dispute")}</DialogTitle>
        </DialogHeader>
        <Textarea
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
