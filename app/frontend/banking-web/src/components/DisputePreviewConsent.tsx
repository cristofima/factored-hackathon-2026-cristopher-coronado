import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { openSupportCase, recoverSupportCase } from "@/api/disputeClient";
import { disputePreviewSchema, type ConversationMessage, type DisputePreview } from "@/api/supportCaseContracts";
import { ApiError, errorTranslationKey } from "@/api/errors";
import { useAuth } from "@/context/AuthContext";
import type { SupportCase } from "@/models/SupportCase";
import { Button } from "@/components/ui/button";
import { disputeTransactionStatus } from "@/common/disputePresentation";

interface Props {
  preview: DisputePreview;
  disabled?: boolean;
  recoveryDisabled?: boolean;
  recoveryOnly?: boolean;
  conversationHistory?: ConversationMessage[];
  onAttempt?: () => void;
  onAccepted?: (supportCase: SupportCase) => void;
  onDeclined?: () => void;
}

export function DisputePreviewConsent({ preview, disabled = false, recoveryDisabled = disabled, recoveryOnly = false, conversationHistory, onAttempt, onAccepted, onDeclined }: Props) {
  const { t, i18n } = useTranslation();
  const { user, sessionKey, logout } = useAuth();
  const scope = JSON.stringify([preview.previewToken, user?.id, user?.identityVersion, sessionKey]);
  const initialScope = useRef(scope);
  const latestScope = useRef(scope);
  latestScope.current = scope;
  const pending = useRef<AbortController | null>(null);
  const attempted = useRef(false);
  const [state, setState] = useState<"ready" | "pending" | "uncertain" | "rejected" | "declined" | "accepted">(recoveryOnly ? "uncertain" : "ready");
  const [recovering, setRecovering] = useState(false);
  const [supportCase, setSupportCase] = useState<SupportCase | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expired, setExpired] = useState(Date.parse(preview.expiresAt) <= Date.now());
  const valid = disputePreviewSchema.safeParse(preview).success && Boolean(user) && initialScope.current === scope;

  useEffect(() => {
    const remaining = Date.parse(preview.expiresAt) - Date.now();
    const timer = Number.isFinite(remaining) ? setTimeout(() => setExpired(true), Math.max(0, remaining)) : undefined;
    return () => { clearTimeout(timer); pending.current?.abort(); };
  }, [scope, preview.expiresAt]);

  async function accept(recover = false) {
    if (!valid || (recover ? recoveryDisabled : disabled || recoveryOnly) || pending.current || state === "declined" || state === "accepted" || state === "rejected") return;
    if (!recover && (attempted.current || Date.parse(preview.expiresAt) <= Date.now())) { setExpired(true); return; }
    attempted.current = true;
    if (!recover) {
      try { onAttempt?.(); } catch { setState("rejected"); setError("chat.recovery.storageUnavailable"); return; }
    }
    const controller = new AbortController();
    pending.current = controller;
    setRecovering(recover); setState("pending"); setError(null);
    const current = () => !controller.signal.aborted && latestScope.current === scope;
    try {
      let result: SupportCase | null;
      try {
        result = recover ? await recoverSupportCase(preview.previewToken, controller.signal)
          : await (conversationHistory === undefined
            ? openSupportCase(preview.previewToken, controller.signal)
            : openSupportCase(preview.previewToken, controller.signal, conversationHistory));
      } catch (cause) {
        if (!current()) return;
        if (cause instanceof ApiError && ["AUTH_REQUIRED", "AUTH_EXPIRED", "AUTH_INVALID"].includes(cause.code)) { logout(); return; }
        if (recover) throw cause;
        if (cause instanceof ApiError && [
          "DISPUTE_PREVIEW_INVALID", "DISPUTE_PREVIEW_EXPIRED", "DISPUTE_PREVIEW_STALE",
          "DISPUTE_UNAVAILABLE", "DISPUTE_INELIGIBLE", "DISPUTE_CARD_ONLY", "DISPUTE_ALREADY_ACTIVE", "ACCESS_DENIED", "INVALID_REQUEST",
        ].includes(cause.code)) {
          setState("rejected");
          setError(cause.code === "DISPUTE_ALREADY_ACTIVE" ? "Dispute preview unavailable" : errorTranslationKey(cause, "Dispute preview unavailable"));
          return;
        }
        // A lost response can follow a committed intake. Never repeat creation.
        result = await recoverSupportCase(preview.previewToken, controller.signal);
      }
      if (!current()) return;
      if (!result || result.transactionId !== preview.transactionId || result.reason !== preview.reason) {
        setState("uncertain"); setError("Dispute acceptance uncertain"); return;
      }
      setSupportCase(result); setState("accepted");
      // Continuation failures must not undo authoritative acceptance.
      try { onAccepted?.(result); } catch { /* The recorded receipt remains authoritative. */ }
    } catch (cause) {
      if (!current()) return;
      if (cause instanceof ApiError && ["AUTH_REQUIRED", "AUTH_EXPIRED", "AUTH_INVALID"].includes(cause.code)) logout();
      setState("uncertain"); setError("Dispute acceptance uncertain");
    } finally { if (pending.current === controller) pending.current = null; }
  }

  if (!valid) return <p>{t("Dispute preview unavailable")}</p>;
  if (state === "declined") return <p>{t("Dispute proposal declined")}</p>;
  if (supportCase) return <section className="rounded-lg border p-4 space-y-3">
    <p>{t("Dispute request recorded")}</p>
    <p>{t(`support-cases.status.${supportCase.status}`, { keySeparator: "." })}</p>
    <Link to={`/support-cases/${encodeURIComponent(supportCase.caseId)}`}>{t("View support case")}</Link>
  </section>;
  const transaction = preview.transaction;
  return <section className="rounded-lg border p-4 space-y-3" aria-label={t("Dispute proposal")}>
    <h3 className="font-semibold">{t("Dispute proposal")}</h3>
    <dl className="grid grid-cols-2 gap-2 text-sm">
      <dt>{t("Amount")}</dt><dd>{transaction.amount ?? t("Not available")} {transaction.currency ?? ""}</dd>
      <dt>{t("Date")}</dt><dd>{transaction.timestamp && Number.isFinite(Date.parse(transaction.timestamp)) ? new Date(transaction.timestamp).toLocaleString(i18n.language) : t("Not available")}</dd>
      <dt>{t("Merchant")}</dt><dd>{transaction.recipientName?.trim() ? transaction.recipientName : t("Not available")}</dd>
      <dt>{t("Card")}</dt><dd>{transaction.product_number ? `•••• ${transaction.product_number.slice(-4)}` : t("Not available")}</dd>
      <dt>{t("Country")}</dt><dd>{transaction.country ?? t("Not available")}</dd>
      <dt>{t("City")}</dt><dd>{transaction.city ?? t("Not available")}</dd>
      <dt>{t("Status")}</dt><dd>{transaction.status ? disputeTransactionStatus(transaction.status, t) : t("Not available")}</dd>
      <dt>{t("Dispute reason")}</dt><dd className="whitespace-pre-wrap">{preview.reason}</dd>
    </dl>
    <p>{t(recoveryOnly || state === "uncertain" ? "Dispute acceptance uncertain" : "Dispute creation consent explanation")}</p>
    {expired && <p role="status">{t("Dispute preview expired")}</p>}
    {error && <p role="alert">{t(error)}</p>}
    {state === "pending" ? <p role="status">{t(recovering ? "Recovering dispute request" : "chat.recovery.creating")}</p> : state === "uncertain" || recoveryOnly ? <Button disabled={recoveryDisabled} onClick={() => void accept(true)}>{t("Recover dispute request")}</Button> : state !== "rejected" && <div className="flex flex-wrap gap-2">
      <Button disabled={disabled || expired || state === "pending"} onClick={() => void accept()}>{t("Create dispute and request human review")}</Button>
      <Button variant="outline" disabled={disabled || state === "pending"} onClick={() => {
        if (!valid || disabled || pending.current || attempted.current) return;
        attempted.current = true;
        setState("declined"); onDeclined?.();
      }}>{t("Decline dispute proposal")}</Button>
    </div>}
  </section>;
}
