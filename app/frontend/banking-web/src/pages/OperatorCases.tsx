import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { claimOperatorCase, getOperatorCase, listOperatorCases, type OperatorCaseView, type OperatorSupportCase } from "@/api/operatorDisputeClient";
import SupportCaseTimeline from "@/components/SupportCaseTimeline";
import { formatDateTime } from "@/common/dateTime";
import { ApiError, errorTranslationKey } from "@/api/errors";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";

export default function OperatorCases() {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const { user, sessionKey, logout } = useAuth();
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const scope = ["operator-cases", sessionKey, user?.id, user?.identityVersion];
  const [offset, setOffset] = useState(0);
  const [view, setView] = useState<OperatorCaseView>("available");
  const queue = useQuery({ queryKey: [...scope, view, "queue", offset], queryFn: ({ signal }) => listOperatorCases(signal, offset, 50, view), retry: false, enabled: !caseId });
  const detail = useQuery({ queryKey: [...scope, caseId], queryFn: ({ signal }) => getOperatorCase(caseId!, signal), retry: false, enabled: !!caseId });
  useEffect(() => {
    if (!caseId && queue.data && offset > 0 && offset >= queue.data.total) {
      setOffset(Math.max(0, Math.ceil(queue.data.total / queue.data.limit) - 1) * queue.data.limit);
    }
  }, [caseId, offset, queue.data]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const pending = useRef<AbortController | null>(null);
  const pendingCase = useRef<string | undefined>(caseId);
  pendingCase.current = caseId;
  useEffect(() => {
    setFailure(null);
    setBusy(false);
    return () => {
      pending.current?.abort();
      pending.current = null;
    };
  }, [caseId, view, sessionKey]);
  const error = failure ?? (caseId ? detail.error : queue.error);
  useEffect(() => {
    if (error instanceof ApiError && error.code === "AUTH_REQUIRED") logout();
  }, [error, logout]);

  const claim = async (supportCase: OperatorSupportCase) => {
    if (pending.current || busy || supportCase.status !== "IN_REVIEW") return;
    const controller = new AbortController();
    pending.current = controller;
    const selectedCase = caseId;
    setBusy(true);
    setFailure(null);
    try {
      const result = await claimOperatorCase(supportCase.caseId, controller.signal);
      controller.signal.throwIfAborted();
      await queryClient.invalidateQueries({ queryKey: scope });
      controller.signal.throwIfAborted();
      if (pendingCase.current === selectedCase) navigate(`/operator/support-cases/${encodeURIComponent(result.caseId)}`);
    } catch (cause) {
      if (controller.signal.aborted) return;
      setFailure(cause);
      if (cause instanceof ApiError && cause.code === "AUTH_REQUIRED") logout();
      if (cause instanceof ApiError && cause.code === "OPERATOR_CLAIM_CONFLICT") {
        await queryClient.invalidateQueries({ queryKey: scope });
      }
    } finally {
      if (pending.current === controller) {
        pending.current = null;
        if (!controller.signal.aborted) setBusy(false);
      }
    }
  };
  const formatTime = (value: string) => formatDateTime(value, user?.locale, "date-time");
  const owned = caseId ? detail.data : undefined;
  const renderCase = (supportCase: OperatorSupportCase) => <Card key={supportCase.caseId} className="flex flex-col">
    <CardHeader className="gap-3 space-y-0">
      <CardTitle className="break-all text-base leading-snug">{supportCase.caseId}</CardTitle>
      <Badge variant="secondary" className="w-fit">{t(`support-cases.status.${supportCase.status}`, { keySeparator: "." })}</Badge>
    </CardHeader>
    <CardContent className="flex-1">
      <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-[minmax(0,9rem)_minmax(0,1fr)] sm:gap-y-3">
        <dt className="font-medium text-muted-foreground">{t("Opened")}</dt>
        <dd className="mb-3 break-words sm:mb-0">{formatTime(supportCase.openedAt)}</dd>
        <dt className="text-xs font-medium text-muted-foreground">{t("Claim version")}</dt>
        <dd className="text-xs tabular-nums">{supportCase.claimVersion}</dd>
      </dl>
    </CardContent>
    <CardFooter className="mt-2 border-t pt-4">
      {view === "assigned"
        ? <Link className="text-sm font-medium underline underline-offset-4" to={`/operator/support-cases/${encodeURIComponent(supportCase.caseId)}`}>{t("View case")}</Link>
        : <Button disabled={busy || supportCase.status !== "IN_REVIEW"} onClick={() => void claim(supportCase)}>{t(busy ? "Taking case..." : "Take case")}</Button>}
    </CardFooter>
  </Card>;

  return <section className="space-y-4">
    <h2 className="text-xl font-semibold">{t("Dispute review queue")}</h2>
    <p className="text-sm text-muted-foreground">{t("Taking a case does not authorize a verdict or financial changes.")}</p>
    {caseId && <Link className="underline" to="/operator/support-cases">{t("Back to review queue")}</Link>}
    {!caseId && <nav aria-label={t("Case views")} className="flex gap-3">
      {(["available", "assigned"] as const).map((item) => <Button key={item} variant={view === item ? "default" : "outline"} aria-pressed={view === item} disabled={busy} onClick={() => { setOffset(0); setView(item); }}>{t(item === "available" ? "Available cases" : "Assigned cases")}</Button>)}
    </nav>}
    {error && <div role="alert"><p>{t(errorTranslationKey(error, "Review queue unavailable"))}</p><Button variant="outline" disabled={busy} onClick={() => { setFailure(null); void (caseId ? detail.refetch() : queue.refetch()); }}>{t("Retry")}</Button></div>}
    {(caseId ? detail.isPending : queue.isPending) && <p role="status">{t("Loading review queue...")}</p>}
    {!caseId && queue.data?.total === 0 && <p>{t(view === "available" ? "No cases awaiting review" : "No assigned cases")}</p>}
    {!caseId && <>
      <div className="grid gap-4 md:grid-cols-2">{queue.data?.items.map(renderCase)}</div>
      {queue.data && <nav aria-label={t("Review queue pages")} className="flex items-center gap-3">
        <Button variant="outline" disabled={busy || offset === 0} onClick={() => setOffset(Math.max(0, offset - queue.data!.limit))}>{t("Previous page")}</Button>
        <p>{t("Total cases")}: {queue.data.total}{queue.data.items.length > 0 && <> · {queue.data.offset + 1}–{queue.data.offset + queue.data.items.length}</>}</p>
        <Button variant="outline" disabled={busy || offset + queue.data.limit >= queue.data.total} onClick={() => setOffset(offset + queue.data!.limit)}>{t("Next page")}</Button>
      </nav>}
    </>}
    {owned && <>
      <Card>
        <CardHeader className="gap-3 space-y-0">
          <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
            <CardTitle className="min-w-0 break-all text-base leading-snug"><Link to={`/operator/support-cases/${encodeURIComponent(owned.caseId)}`}>{owned.caseId}</Link></CardTitle>
            <Badge variant="secondary" className="shrink-0">{t(`support-cases.status.${owned.status}`, { keySeparator: "." })}</Badge>
          </div>
          <p className="text-sm text-muted-foreground">{t("Assigned to you")}</p>
        </CardHeader>
        <CardContent className="space-y-6">
          <dl className="rounded-md border bg-muted/30 p-4">
            <dt className="text-xs font-semibold text-muted-foreground">{t("Reason")}</dt>
            <dd className="mt-2 whitespace-pre-wrap break-words text-base leading-relaxed">{owned.reason}</dd>
          </dl>
          <dl className="grid grid-cols-1 gap-x-6 gap-y-1 border-t pt-4 text-sm sm:grid-cols-[minmax(0,11rem)_minmax(0,1fr)] sm:gap-y-3">
            <dt className="font-medium text-muted-foreground">{t("Claimed at")}</dt>
            <dd className="mb-3 break-words sm:mb-0">{formatTime(owned.claimedAt)}</dd>
            <dt className="text-xs font-medium text-muted-foreground">{t("Claim version")}</dt>
            <dd className="text-xs tabular-nums">{owned.claimVersion}</dd>
          </dl>
        </CardContent>
      </Card>
      <SupportCaseTimeline events={owned.events} transactionId={owned.transactionId} perspective="operator" />
    </>}
  </section>;
}
