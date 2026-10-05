import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { adjudicateOperatorCase, retryOperatorEffects, protectOperatorCard, type OperatorCaseDetail } from "@/api/operatorDisputeClient";
import { ApiError, errorTranslationKey } from "@/api/errors";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { formatDateTime } from "@/common/dateTime";
import { maskedCardNumber } from "@/common/products";
import { formatProductAmount } from "@/common/productAmount";
import { disputeProductLabel, disputeTransactionStatus, disputeProtectionStatus, disputeSourceLabel, formatStoredScore } from "@/common/disputePresentation";

type Action = "valid" | "invalid" | "retry" | "block" | "unblock";
const evidenceGroups = [
  { title: "Source evidence", keys: ["transactionId", "productId", "productType", "customerId", "amount", "currency", "transactionDate", "status", "merchant", "country", "city", "responseCode", "sourceKind"] },
  { title: "Stored routing signal", keys: ["fraudScore", "isFraud"] },
];
export default function OperatorCaseActions({ supportCase }: { supportCase: OperatorCaseDetail }) {
  const { t } = useTranslation();
  const { user, sessionKey, logout } = useAuth();
  const queryClient = useQueryClient();
  const [rationale, setRationale] = useState("");
  const [destination, setDestination] = useState("");
  const [confirmation, setConfirmation] = useState<Action | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const pending = useRef<AbortController | null>(null);
  useEffect(() => {
    setRationale(""); setDestination(""); setConfirmation(null); setFailure(null); setBusy(false);
    return () => { pending.current?.abort(); pending.current = null; };
  }, [supportCase.caseId, supportCase.caseVersion, sessionKey, user?.id, user?.identityVersion]);
  const scope = ["operator-cases", sessionKey, user?.id, user?.identityVersion];
  const choices = supportCase.eligibleDestinations ?? [];
  const version = supportCase.caseVersion;
  const evidenceVersion = supportCase.evidenceVersion;
  const ready = version !== undefined && supportCase.assignedOperatorSub === user?.id;
  const reasonReady = !!rationale.trim() && rationale.trim().length <= 1000;
  const protectionStatus = supportCase.productProtectionStatus;
  const protectionReady = typeof protectionStatus === "string" && protectionStatus.trim().length > 0;
  const isBlocked = protectionStatus?.toLowerCase() === "blocked";
  const destinationReady = choices.length <= 1 || !!destination;
  const destinationLabel = (choice: (typeof choices)[number]) => ["Debit Card", "Credit Card"].includes(choice.productType)
    ? maskedCardNumber(choice.productNumber) ?? t("Unavailable")
    : choice.productNumber ?? choice.productId;
  const selectedDestination = choices.find((choice) => choice.productId === destination) ?? (choices.length === 1 ? choices[0] : undefined);
  const execute = async () => {
    if (!confirmation || !ready || version === undefined || pending.current) return;
    if ((confirmation === "valid" || confirmation === "invalid") && (!evidenceVersion || !reasonReady || !supportCase.evidence)) return;
    if (confirmation === "retry" && !destinationReady) return;
    if ((confirmation === "block" || confirmation === "unblock") && (!reasonReady || !protectionReady)) return;
    const action = confirmation;
    const controller = new AbortController(); pending.current = controller;
    setBusy(true); setFailure(null); setConfirmation(null);
    try {
      const base = { expected_case_version: version };
      if (action === "valid" || action === "invalid") {
        await adjudicateOperatorCase(supportCase.caseId, { ...base, expected_evidence_version: evidenceVersion as number, verdict: action, rationale, ...(destination ? { destination_product_id: destination } : {}) }, controller.signal);
      } else if (action === "retry") {
        await retryOperatorEffects(supportCase.caseId, { ...base, ...(destination ? { destination_product_id: destination } : {}) }, controller.signal);
      } else {
        await protectOperatorCard(supportCase.caseId, { ...base, blocked: action === "block", rationale }, controller.signal);
      }
      controller.signal.throwIfAborted();
      await queryClient.invalidateQueries({ queryKey: scope });
    } catch (error) {
      if (!controller.signal.aborted) {
        setFailure(error);
        if (error instanceof ApiError && error.code === "AUTH_REQUIRED") logout();
        await queryClient.invalidateQueries({ queryKey: scope });
      }
    } finally {
      if (pending.current === controller) { pending.current = null; if (!controller.signal.aborted) setBusy(false); }
    }
  };
  const evidence = supportCase.evidence;
  return <Card>
    <CardHeader><CardTitle>{t("Review evidence and actions")}</CardTitle></CardHeader>
    <CardContent className="space-y-4">
      <p>{t("Case version")}: {version ?? t("Unavailable")} · {t("Evidence version")}: {evidenceVersion ?? t("Unavailable")}</p>
      {!evidence && <p role="alert">{t("Verified evidence is unavailable. No financial completion is confirmed.")}</p>}
      {evidence && <p>{t("Stored transaction data supports review; it does not prove the dispute is valid.")}</p>}
      {evidence && evidenceGroups.map(group => <section key={group.title} className="space-y-2">
        <h3 className="font-semibold">{t(group.title)}</h3>
        {group.title === "Stored routing signal" && <p>{t("This stored synthetic signal is for routing only, not an investigation or proof of legitimacy.")}</p>}
        <dl className="grid gap-2 sm:grid-cols-2">
          {group.keys.map(key => {
            const value = evidence[key as keyof typeof evidence];
            const display = value == null || value === "" ? t("Unavailable") : typeof value === "boolean" ? t(value ? "Yes" : "No")
              : key === "transactionDate" ? formatDateTime(String(value), user?.locale, "date-time")
              : key === "productType" ? disputeProductLabel(String(value), t)
              : key === "status" ? disputeTransactionStatus(String(value), t)
              : key === "sourceKind" ? disputeSourceLabel(String(value), t)
              : key === "amount" ? formatProductAmount(String(value), user?.locale ?? "en")
              : key === "fraudScore" ? formatStoredScore(String(value), user?.locale ?? "en") : String(value);
            return <div key={key}><dt className="text-muted-foreground">{t(`operator.evidence.${key}`, { keySeparator: "." })}</dt><dd className="break-words">{display}</dd></div>;
          })}
        </dl>
      </section>)}
      <section className="space-y-2">
        <h3 className="font-semibold">{t("Missing information")}</h3>
        {!evidence ? <p>{t("Unavailable")}</p> : <p>{evidenceGroups.flatMap(group => group.keys).filter(key => evidence[key as keyof typeof evidence] == null || evidence[key as keyof typeof evidence] === "").map(key => t(`operator.evidence.${key}`, { keySeparator: "." })).join(", ") || t("No missing fields in the recorded snapshot")}</p>}
      </section>
      <h3 className="font-semibold">{t("Verdict and recorded effects")}</h3>
      {supportCase.verdict && <p>{t("Final verdict")}: {t(supportCase.verdict === "valid" ? "Valid dispute" : "Invalid dispute")}</p>}
      {supportCase.rationale && <p className="whitespace-pre-wrap">{t("Rationale")}: {supportCase.rationale}</p>}
      {supportCase.effects && <div role="status" className="space-y-1">
        <p>{t("Full original-currency restitution posted. Credit-card adjustments reduce debt.")}</p>
        <p>{t("This recorded application movement does not confirm external settlement.")}</p>
        <p>{t("Financial movement")}: {supportCase.effects.movementId}</p>
        <p>{t("Destination product")}: {supportCase.effects.destinationProductId}</p>
        <p>{t("Amount")}: {formatProductAmount(supportCase.effects.amount, user?.locale ?? "en")} {supportCase.effects.currency}</p>
        <p>{t("Recorded balance adjustment")}: {formatProductAmount(supportCase.effects.balanceDelta, user?.locale ?? "en")} {supportCase.effects.currency}</p>
        <p>{t("Executed")}: {formatDateTime(supportCase.effects.executedAt, user?.locale, "date-time")}</p>
      </div>}
      {supportCase.status === "PENDING_EFFECTS" && <p role="status">{t("Restitution is pending. No completed credit or balance change is confirmed.")} {t(`operator.effects.${supportCase.effectCode ?? "PENDING"}`, { keySeparator: ".", defaultValue: t("Financial execution is pending") })}</p>}
      {ready && evidence && (supportCase.status === "IN_REVIEW" || supportCase.status === "PENDING_EFFECTS") && <>
        <label className="block" htmlFor="restitution-destination">{t("Restitution destination")}</label>
        <select id="restitution-destination" className="w-full rounded-md border bg-background p-2" disabled={busy} value={destination} onChange={(event) => setDestination(event.target.value)}>
          <option value="">{t(choices.length > 1 ? "Select an eligible destination" : choices.length === 1 ? "Use the single eligible destination" : "No eligible destination")}</option>
          {choices.map((choice) => <option key={choice.productId} value={choice.productId}>{disputeProductLabel(choice.productType, t)} · {destinationLabel(choice)} · {choice.currency}</option>)}
        </select>
        {supportCase.status === "PENDING_EFFECTS" && <Button disabled={busy || !destinationReady} onClick={() => setConfirmation("retry")}>{t("Retry financial effects")}</Button>}
      </>}
      {ready && <>
        <label className="block" htmlFor="operator-rationale">{t("Mandatory rationale")}</label>
        <Textarea id="operator-rationale" maxLength={1000} value={rationale} disabled={busy} onChange={(event) => setRationale(event.target.value)} />
        {supportCase.status === "IN_REVIEW" && <div className="flex gap-2">
          <Button disabled={busy || !reasonReady || !evidence || !evidenceVersion} onClick={() => setConfirmation("valid")}>{t("Valid dispute")}</Button>
          <Button variant="outline" disabled={busy || !reasonReady || !evidence || !evidenceVersion} onClick={() => setConfirmation("invalid")}>{t("Invalid dispute")}</Button>
        </div>}
        <p>{t("Card protection is a separate audited action. It only affects this application, not the processor or card network.")}</p>
        <p>{t("Current card state")}: {protectionReady ? disputeProtectionStatus(protectionStatus, t) : t("Unavailable")}</p>
        {!supportCase.cardProtection && <p>{t("No recorded protection action")}</p>}
        {supportCase.cardProtection && <p>{t("Recorded prior status")}: {disputeProtectionStatus(supportCase.cardProtection.priorStatus, t)} · {t("Rationale")}: {supportCase.cardProtection.rationale}</p>}
        <Button variant="outline" disabled={busy || !reasonReady || !protectionReady} onClick={() => setConfirmation(isBlocked ? "unblock" : "block")}>{t(isBlocked ? "Unblock in application" : "Block in application")}</Button>
      </>}
      {failure && <p role="alert">{t(errorTranslationKey(failure, "Could not apply operator action"))}</p>}
      <AlertDialog open={confirmation !== null} onOpenChange={(open) => { if (!open) setConfirmation(null); }}>
        <AlertDialogContent><AlertDialogHeader><AlertDialogTitle>{t("Confirm operator action")}</AlertDialogTitle><AlertDialogDescription>{t("This action records an auditable decision using the displayed case and evidence versions. Financial execution may remain pending; protection never implies processor changes.")}</AlertDialogDescription></AlertDialogHeader>
          <p>{t("Case version")}: {version} · {t("Evidence version")}: {evidenceVersion}</p>
          <p>{t("Action")}: {t(confirmation === "valid" ? "Valid dispute" : confirmation === "invalid" ? "Invalid dispute" : confirmation === "retry" ? "Retry financial effects" : confirmation === "block" ? "Block in application" : "Unblock in application")}</p>
          {confirmation !== "retry" && <p className="whitespace-pre-wrap">{t("Rationale")}: {rationale.trim()}</p>}
          {(confirmation === "valid" || confirmation === "retry") && <p>{t("Restitution destination")}: {selectedDestination ? destinationLabel(selectedDestination) : t(choices.length > 1 ? "Select an eligible destination" : "No eligible destination")}</p>}
          {(confirmation === "block" || confirmation === "unblock") && <p>{t("Current card state")}: {protectionReady ? disputeProtectionStatus(protectionStatus, t) : t("Unavailable")}</p>}
          <AlertDialogFooter><AlertDialogCancel>{t("Cancel")}</AlertDialogCancel><AlertDialogAction disabled={busy} onClick={() => void execute()}>{t("Confirm")}</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </CardContent>
  </Card>;
}
