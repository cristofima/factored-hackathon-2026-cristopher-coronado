import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { openSupportCase, recoverSupportCase } from "@/api/disputeClient";
import { disputePreviewSchema, type DisputePreview } from "@/api/supportCaseContracts";
import { ApiError, errorTranslationKey } from "@/api/errors";
import { useAuth } from "@/context/AuthContext";
import type { SupportCase } from "@/models/SupportCase";
import { Button } from "@/components/ui/button";

interface Props {
  preview: DisputePreview;
  disabled?: boolean;
  onAccepted?: (supportCase: SupportCase) => void;
  onDeclined?: () => void;
}

export function DisputePreviewConsent({ preview, disabled = false, onAccepted, onDeclined }: Props) {
  const { t, i18n } = useTranslation();
  const { user, sessionKey, logout } = useAuth();
  const scope = JSON.stringify([preview.previewToken, user?.id, user?.identityVersion, sessionKey]);
  const initialScope = useRef(scope);
  const latestScope = useRef(scope);
  latestScope.current = scope;
  const pending = useRef<AbortController | null>(null);
  const attempted = useRef(false);
  const [state, setState] = useState<"ready" | "pending" | "uncertain" | "rejected" | "declined" | "accepted">("ready");
  const [supportCase, setSupportCase] = useState<SupportCase | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expired, setExpired] = useState(Date.parse(preview.expiresAt) <= Date.now());
  const valid = disputePreviewSchema.safeParse(preview).success && Boolean(user) && initialScope.current === scope;

  useEffect(() => {
    const remaining = Date.parse(preview.expiresAt) - Date.now();
    const timer = Number.isFinite(remaining) ? setTimeout(() => setExpired(true), Math.max(0, remaining)) : undefined;
    return () => { clearTimeout(timer); pending.current?.abort(); };
  }, [scope, preview.expiresAt]);

  async function accept(recoveryOnly = false) {
    if (!valid || disabled || pending.current || state === "declined" || state === "accepted" || state === "rejected") return;
    if (!recoveryOnly && (attempted.current || Date.parse(preview.expiresAt) <= Date.now())) { setExpired(true); return; }
    attempted.current = true;
    const controller = new AbortController();
    pending.current = controller;
    setState("pending"); setError(null);
    const current = () => !controller.signal.aborted && latestScope.current === scope;
    try {
      let result: SupportCase | null;
      try {
        result = recoveryOnly ? await recoverSupportCase(preview.previewToken, controller.signal)
          : await openSupportCase(preview.previewToken, controller.signal);
      } catch (cause) {
        if (!current()) return;
        if (cause instanceof ApiError && ["AUTH_REQUIRED", "AUTH_EXPIRED", "AUTH_INVALID"].includes(cause.code)) { logout(); return; }
        if (recoveryOnly) throw cause;
        if (cause instanceof ApiError && [
          "DISPUTE_PREVIEW_INVALID", "DISPUTE_PREVIEW_EXPIRED", "DISPUTE_PREVIEW_STALE",
          "DISPUTE_UNAVAILABLE", "DISPUTE_INELIGIBLE", "DISPUTE_CARD_ONLY", "DISPUTE_ALREADY_ACTIVE", "ACCESS_DENIED",
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
    <p>{t(`support-cases.status.${supportCase.status}`)}</p>
    <Link to={`/support-cases/${supportCase.caseId}`}>{t("View support case")}</Link>
  </section>;
  const transaction = preview.transaction;
  return <section className="rounded-lg border p-4 space-y-3" aria-label={t("Dispute proposal")}>
    <h3 className="font-semibold">{t("Dispute proposal")}</h3>
    <dl className="grid grid-cols-2 gap-2 text-sm">
      <dt>{t("Amount")}</dt><dd>{transaction.amount ?? t("Not available")} {transaction.currency ?? ""}</dd>
      <dt>{t("Date")}</dt><dd>{transaction.timestamp && Number.isFinite(Date.parse(transaction.timestamp)) ? new Date(transaction.timestamp).toLocaleString(i18n.language) : t("Not available")}</dd>
      <dt>{t("Merchant")}</dt><dd>{transaction.description ?? t("Not available")}</dd>
      <dt>{t("Card")}</dt><dd>{transaction.product_number ? `•••• ${transaction.product_number.slice(-4)}` : t("Not available")}</dd>
      <dt>{t("Country")}</dt><dd>{transaction.country ?? t("Not available")}</dd>
      <dt>{t("City")}</dt><dd>{transaction.city ?? t("Not available")}</dd>
      <dt>{t("Status")}</dt><dd>{transaction.status ? t(`transactions.statuses.${transaction.status}`, { defaultValue: t("Not available") }) : t("Not available")}</dd>
      <dt>{t("Dispute reason")}</dt><dd className="whitespace-pre-wrap">{preview.reason}</dd>
    </dl>
    <p>{t("Dispute creation consent explanation")}</p>
    {expired && <p role="status">{t("Dispute preview expired")}</p>}
    {error && <p role="alert">{t(error)}</p>}
    {state === "uncertain" ? <Button disabled={disabled} onClick={() => void accept(true)}>{t("Recover dispute request")}</Button> : state !== "rejected" && <div className="flex flex-wrap gap-2">
      <Button disabled={disabled || expired || state === "pending"} onClick={() => void accept()}>{t("Create dispute and request human review")}</Button>
      <Button variant="outline" disabled={disabled || state === "pending"} onClick={() => {
        if (!valid || disabled || pending.current || attempted.current) return;
        attempted.current = true;
        setState("declined"); onDeclined?.();
      }}>{t("Decline dispute proposal")}</Button>
    </div>}
  </section>;
}
