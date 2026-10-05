import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { listSupportCases } from "@/api/disputeClient";
import { isTerminalCase } from "@/api/supportCaseContracts";
import { startDisputePolling } from "@/api/disputePolling";
import { ApiError, errorTranslationKey } from "@/api/errors";
import type { SupportCase } from "@/models/SupportCase";
import { useAuth } from "@/context/AuthContext";
import { formatDateTime } from "@/common/dateTime";

export default function SupportCases() {
  const { t } = useTranslation();
  const { user, sessionKey, logout } = useAuth();
  const [cases, setCases] = useState<SupportCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    setCases([]);
    setLoading(true);
  }, [user?.id, sessionKey, user?.identityVersion]);

  useEffect(() => {
    setError(null);
    return startDisputePolling((signal) =>
      listSupportCases(signal)
        .then((result) => {
          if (!signal.aborted) {
            setCases(result);
            setError(null);
          }
        })
        .catch((cause: unknown) => {
          if (!signal.aborted) {
            if (cause instanceof ApiError && cause.code === "AUTH_REQUIRED") logout();
            setError(
              errorTranslationKey(cause, "Support cases are unavailable"),
            );
          }
        })
        .finally(() => {
          if (!signal.aborted) setLoading(false);
        }),
    );
  }, [user?.id, sessionKey, user?.identityVersion, attempt, logout]);

  return (
    <div className="p-6 max-w-5xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground">
          {t("Transaction Disputes")}
        </h1>
        {(error || !loading) && (
          <Button
            variant="outline"
            onClick={() => setAttempt((value) => value + 1)}
          >
            <RefreshCw className="mr-2 h-4 w-4" aria-hidden="true" />
            {t("Refresh")}
          </Button>
        )}
      </div>
      <p className="max-w-3xl text-sm text-muted-foreground">
        {t("Support cases description")}
      </p>
      {loading && (
        <output className="block">{t("Loading support cases...")}</output>
      )}
      {error && <div role="alert">{t(error)}</div>}
      {!loading && !error && cases.length === 0 && (
        <output className="block">{t("No support cases yet.")}</output>
      )}
      {cases.length > 0 && (
        <div className="space-y-3">
          {cases.map((item) => (
            <Link key={item.caseId} to={`/support-cases/${item.caseId}`}>
              <Card className="transition-colors hover:bg-muted/40">
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-base font-mono">
                    {item.caseId}
                  </CardTitle>
                  <Badge
                    variant={
                      isTerminalCase(item.status) ? "secondary" : "default"
                    }
                  >
                    {t(`support-cases.status.${item.status}`, {
                      keySeparator: ".",
                      defaultValue: item.status,
                    })}
                  </Badge>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground space-y-1">
                  <p className="break-words">{item.reason}</p>
                  <p>
                    {t("Opened")}: {formatDateTime(item.openedAt, user?.locale, "date-time")}
                    {item.productNumber ? ` · ${item.productNumber}` : ""}
                  </p>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
