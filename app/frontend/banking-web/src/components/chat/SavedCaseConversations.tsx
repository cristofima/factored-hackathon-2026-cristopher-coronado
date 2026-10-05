import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { listSupportCases } from "@/api/disputeClient";
import { ApiError } from "@/api/errors";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import SupportCaseConversation from "@/components/SupportCaseConversation";

export function SavedCaseConversations() {
  const { t } = useTranslation();
  const { user, sessionKey, logout } = useAuth();
  const scope = JSON.stringify([user?.id, user?.identityVersion, sessionKey]);
  const [selection, setSelection] = useState<{ scope: string; caseId: string } | null>(null);
  const cases = useQuery({
    queryKey: ["help-case-conversations", user?.id, user?.identityVersion, sessionKey],
    queryFn: ({ signal }) => listSupportCases(signal),
    enabled: user?.role === "customer", retry: false, gcTime: 0,
  });
  useEffect(() => {
    if (cases.error instanceof ApiError && cases.error.code === "AUTH_REQUIRED") logout();
  }, [cases.error, logout]);
  if (user?.role !== "customer") return null;
  const selected = !cases.error && selection?.scope === scope
    ? cases.data?.find(item => item.caseId === selection.caseId) : undefined;

  return <section aria-label={t("Saved case conversations")} className="space-y-3 p-4">
    <h2 className="text-sm font-semibold">{t("Saved case conversations")}</h2>
    <p className="text-xs text-muted-foreground">{t("Saved case conversations description")}</p>
    {cases.isPending && <p role="status">{t("Loading support cases...")}</p>}
    {cases.error && <div role="alert" className="space-y-2">
      <p>{t("Conversation unavailable")}</p>
      <Button variant="outline" onClick={() => void cases.refetch()}>{t("Retry")}</Button>
    </div>}
    {!cases.isPending && !cases.error && cases.data?.length === 0 && <p>{t("No support cases yet.")}</p>}
    {!cases.error && cases.data && <ul className="grid gap-2 sm:grid-cols-2">
      {cases.data.map(item => <li key={item.caseId}>
        <Button variant={selected?.caseId === item.caseId ? "secondary" : "outline"}
          className="h-auto w-full min-w-0 flex-wrap justify-start whitespace-normal p-3 text-left"
          aria-pressed={selected?.caseId === item.caseId}
          onClick={() => setSelection({ scope, caseId: item.caseId })}>
          <span className="min-w-0 font-mono [overflow-wrap:anywhere]">{item.caseId}</span>
          <Badge variant="outline">{t(`support-cases.status.${item.status}`, { keySeparator: ".", defaultValue: item.status })}</Badge>
        </Button>
      </li>)}
    </ul>}
    {selected && <div className="space-y-2" key={`${scope}:${selected.caseId}`}>
      <Button asChild variant="link"><Link to={`/support-cases/${encodeURIComponent(selected.caseId)}`}>{t("View support case")}</Link></Button>
      <SupportCaseConversation caseId={selected.caseId} />
    </div>}
  </section>;
}
