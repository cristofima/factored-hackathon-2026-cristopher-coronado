import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  dismissSupportCaseRecommendation,
  getSupportCaseDetail,
  respondToSupportCaseApproval,
} from "@/api/disputeClient";
import { ApiError, errorTranslationKey } from "@/api/errors";
import { isTerminalCase } from "@/api/supportCaseContracts";
import { startDisputePolling } from "@/api/disputePolling";
import { useAuth } from "@/context/AuthContext";
import type { SupportCase, SupportCaseEvent } from "@/models/SupportCase";
import SupportCaseTimeline from "@/components/SupportCaseTimeline";
import SupportCaseFinancialDetails from "@/components/SupportCaseFinancialDetails";
import SupportCaseIntakeReceipt from "@/components/SupportCaseIntakeReceipt";
import { maskedCardNumber } from "@/common/products";

export default function SupportCaseDetail() {
  const { t } = useTranslation();
  const { caseId } = useParams<{ caseId: string }>();
  const { user, sessionKey, logout } = useAuth();
  const [supportCase, setSupportCase] = useState<SupportCase | null>(null);
  const [timeline, setTimeline] = useState<SupportCaseEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const actionInFlight = useRef(false);
  const stopPolling = useRef<(() => void) | null>(null);
  const actionScope = useRef(0);
  const actionController = useRef<AbortController | null>(null);

  useEffect(() => {
    setSupportCase(null);
    setTimeline([]);
    setLoading(true);
    setActionError(null);
    setActionPending(false);
    actionInFlight.current = false;
    return () => {
      actionScope.current += 1;
      actionController.current?.abort();
    };
  }, [caseId, user?.id, user?.identityVersion, sessionKey]);

  useEffect(() => {
    if (!caseId || actionPending) return;
    setError(null);
    const stop = startDisputePolling((signal) =>
      getSupportCaseDetail(caseId, signal)
        .then(([caseResult, timelineResult]) => {
          if (!signal.aborted) {
            setSupportCase(caseResult);
            setTimeline(timelineResult);
            setError(null);
          }
        })
        .catch((cause: unknown) => {
          if (!signal.aborted) {
            if (cause instanceof ApiError && cause.code === "AUTH_REQUIRED") logout();
            setError(errorTranslationKey(cause, "Support case is unavailable"));
          }
        })
        .finally(() => {
          if (!signal.aborted) setLoading(false);
        }),
    );
    stopPolling.current = stop;
    return stop;
  }, [caseId, user?.id, user?.identityVersion, sessionKey, attempt, actionPending, logout]);

  const respond = async (approved: boolean) => {
    if (!caseId || actionInFlight.current) return;
    actionInFlight.current = true;
    stopPolling.current?.();
    const scope = actionScope.current;
    const controller = new AbortController();
    actionController.current = controller;
    setActionPending(true);
    setActionError(null);
    try {
      const updated = await respondToSupportCaseApproval(caseId, approved, controller.signal);
      if (scope !== actionScope.current) return;
      setSupportCase(updated);
    } catch (cause) {
      if (!controller.signal.aborted && cause instanceof ApiError && cause.code === "AUTH_REQUIRED") logout();
      if (scope === actionScope.current)
        setActionError(
          errorTranslationKey(cause, "Could not record your response"),
        );
    } finally {
      if (scope === actionScope.current) {
        actionInFlight.current = false;
        setActionPending(false);
      }
    }
  };

  const dismissRecommendation = async () => {
    if (!caseId || actionInFlight.current) return;
    actionInFlight.current = true;
    stopPolling.current?.();
    const scope = actionScope.current;
    const controller = new AbortController();
    actionController.current = controller;
    setActionPending(true);
    setActionError(null);
    try {
      const updated = await dismissSupportCaseRecommendation(caseId, controller.signal);
      if (scope === actionScope.current) setSupportCase(updated);
    } catch (cause) {
      if (!controller.signal.aborted && cause instanceof ApiError && cause.code === "AUTH_REQUIRED") logout();
      if (scope === actionScope.current)
        setActionError(
          errorTranslationKey(cause, "Could not dismiss the recommendation"),
        );
    } finally {
      if (scope === actionScope.current) {
        actionInFlight.current = false;
        setActionPending(false);
      }
    }
  };

  return (
    <div className="min-w-0 p-4 sm:p-6 max-w-4xl space-y-6">
      <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="min-w-0 text-2xl font-bold text-foreground font-mono [overflow-wrap:anywhere]">
          {caseId}
        </h1>
        <Button
          variant="outline"
          disabled={actionPending}
          onClick={() => setAttempt((value) => value + 1)}
        >
          <RefreshCw className="mr-2 h-4 w-4" aria-hidden="true" />
          {t("Refresh")}
        </Button>
      </div>
      {loading && (
        <output className="block">{t("Loading support case...")}</output>
      )}
      {error && <div role="alert">{t(error)}</div>}
      {supportCase && (
        <>
          <Card>
            <CardHeader className="flex flex-wrap flex-row items-center justify-between gap-2 space-y-0">
              <CardTitle className="text-base">{t("Case Details")}</CardTitle>
              <Badge
                variant={
                  isTerminalCase(supportCase.status) ? "secondary" : "default"
                }
              >
                {t(`support-cases.status.${supportCase.status}`, {
                  keySeparator: ".",
                  defaultValue: supportCase.status,
                })}
              </Badge>
            </CardHeader>
            <CardContent className="text-sm space-y-2">
              <SupportCaseIntakeReceipt supportCase={supportCase} events={timeline} />
              {supportCase.productNumber && (
                <p>
                  <span className="text-muted-foreground">
                    {t("Card Number")}:{" "}
                  </span>
                  {maskedCardNumber(supportCase.productNumber) ?? t("Unavailable")}
                </p>
              )}
              {supportCase.resolutionOutcome && (
                <p>
                  <span className="text-muted-foreground">
                    {t("Resolution")}:{" "}
                  </span>
                  {t(
                    `support-cases.resolution.${supportCase.resolutionOutcome}`,
                    {
                      keySeparator: ".",
                      defaultValue: t("Not available"),
                    },
                  )}
                </p>
              )}
            </CardContent>
          </Card>

          {supportCase.status === "WAITING_USER_APPROVAL" && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  {t("Approval Needed")}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  {t("Dispute approval prompt")}
                </p>
                {actionError && <div role="alert">{t(actionError)}</div>}
                <div className="flex flex-wrap gap-3">
                  <Button
                    disabled={actionPending}
                    onClick={() => respond(true)}
                  >
                    {t("Approve dispute")}
                  </Button>
                  <Button
                    variant="outline"
                    disabled={actionPending}
                    onClick={() => respond(false)}
                  >
                    {t("Decline")}
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {supportCase.recommendationType &&
            !supportCase.recommendationOptedOut && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">
                    {t("Recommendation")}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm">
                    {t(
                      `support-cases.recommendations.${supportCase.recommendationType}`,
                      {
                        keySeparator: ".",
                        defaultValue: t("Not available"),
                      },
                    )}
                  </p>
                  {actionError && <div role="alert">{t(actionError)}</div>}
                  <Button
                    variant="outline"
                    disabled={actionPending}
                    onClick={dismissRecommendation}
                  >
                    {t("Dismiss recommendation")}
                  </Button>
                </CardContent>
              </Card>
            )}

          <SupportCaseFinancialDetails supportCase={supportCase} />
          <SupportCaseTimeline events={timeline} transactionId={supportCase.transactionId} />
        </>
      )}
    </div>
  );
}
