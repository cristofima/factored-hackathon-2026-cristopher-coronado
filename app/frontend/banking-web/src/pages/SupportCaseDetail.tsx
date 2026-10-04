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
import { errorTranslationKey } from "@/api/errors";
import { startDisputePolling } from "@/api/disputePolling";
import { useAuth } from "@/context/AuthContext";
import type { SupportCase, SupportCaseEvent } from "@/models/SupportCase";
import { supportCaseEventMessageKey } from "@/models/SupportCase";

export default function SupportCaseDetail() {
  const { t } = useTranslation();
  const { caseId } = useParams<{ caseId: string }>();
  const { user } = useAuth();
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

  useEffect(() => {
    setSupportCase(null);
    setTimeline([]);
    setLoading(true);
    setActionError(null);
    setActionPending(false);
    actionInFlight.current = false;
    return () => {
      actionScope.current += 1;
    };
  }, [caseId, user?.id]);

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
            setError(errorTranslationKey(cause, "Support case is unavailable"));
          }
        })
        .finally(() => {
          if (!signal.aborted) setLoading(false);
        }),
    );
    stopPolling.current = stop;
    return stop;
  }, [caseId, user?.id, attempt, actionPending]);

  const respond = async (approved: boolean) => {
    if (!caseId || actionInFlight.current) return;
    actionInFlight.current = true;
    stopPolling.current?.();
    const scope = actionScope.current;
    setActionPending(true);
    setActionError(null);
    try {
      const updated = await respondToSupportCaseApproval(caseId, approved);
      if (scope !== actionScope.current) return;
      setSupportCase(updated);
    } catch (cause) {
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
    setActionPending(true);
    setActionError(null);
    try {
      const updated = await dismissSupportCaseRecommendation(caseId);
      if (scope === actionScope.current) setSupportCase(updated);
    } catch (cause) {
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
    <div className="p-6 max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground font-mono">
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
            <CardHeader className="flex flex-row items-center justify-between space-y-0">
              <CardTitle className="text-base">{t("Case Details")}</CardTitle>
              <Badge
                variant={
                  supportCase.status === "RESOLVED" ? "secondary" : "default"
                }
              >
                {t(`support-cases.status.${supportCase.status}`, {
                  keySeparator: ".",
                  defaultValue: supportCase.status,
                })}
              </Badge>
            </CardHeader>
            <CardContent className="text-sm space-y-2">
              <p>
                <span className="text-muted-foreground">{t("Reason")}: </span>
                {supportCase.reason}
              </p>
              {supportCase.productNumber && (
                <p>
                  <span className="text-muted-foreground">
                    {t("Card Number")}:{" "}
                  </span>
                  {supportCase.productNumber}
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
                      defaultValue: supportCase.resolutionOutcome,
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
                <div className="flex gap-3">
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

          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("Timeline")}</CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="space-y-3">
                {timeline.map((event, index) => (
                  <li
                    key={`${event.eventType}-${index}`}
                    className="text-sm border-l-2 pl-3"
                  >
                    <p className="font-medium">
                      {t(`support-cases.events.${event.eventType}`, {
                        keySeparator: ".",
                        defaultValue: event.eventType,
                      })}
                    </p>
                    {(event.displayMessage ?? event.message) && (
                      <p className="text-muted-foreground">
                        {t(supportCaseEventMessageKey(event), {
                          keySeparator: ".",
                          transactionId: supportCase.transactionId,
                          defaultValue: event.displayMessage ?? event.message ?? t("Not available"),
                        })}
                      </p>
                    )}
                    <p className="text-xs text-muted-foreground">
                      {event.createdAt.slice(0, 19).replace("T", " ")}
                    </p>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
