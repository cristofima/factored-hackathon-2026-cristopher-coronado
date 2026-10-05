import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getCaseConversation } from "@/api/disputeClient";
import { getOperatorCaseConversation } from "@/api/operatorDisputeClient";
import { ApiError } from "@/api/errors";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Markdown } from "@/components/chat/Markdown";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";

export default function SupportCaseConversation({ caseId, operator = false }: { caseId: string; operator?: boolean }) {
  const { user, sessionKey, logout } = useAuth();
  const { t } = useTranslation();
  const history = useQuery({
    queryKey: ["case-conversation", operator, caseId, sessionKey, user?.id, user?.identityVersion],
    queryFn: ({ signal }) => (operator ? getOperatorCaseConversation : getCaseConversation)(caseId, signal),
    enabled: Boolean(user), retry: false, gcTime: 0,
  });
  useEffect(() => {
    if (history.error instanceof ApiError && history.error.code === "AUTH_REQUIRED") logout();
  }, [history.error, logout]);
  if (!user) return null;
  return <Card>
    <Accordion type="single" collapsible key={`${caseId}:${sessionKey}:${user.id}:${user.identityVersion}`}>
      <AccordionItem value="conversation" className="border-b-0">
        <AccordionTrigger className="px-6 text-base">{t("Case conversation")}</AccordionTrigger>
        <AccordionContent>
          <CardContent className="space-y-3 pb-0">
            <p className="text-sm text-muted-foreground">{t("Case conversation provenance")}</p>
            {history.isPending && <p role="status">{t("Loading conversation...")}</p>}
            {history.error && <div role="alert"><p>{t("Conversation unavailable")}</p><Button variant="outline" onClick={() => void history.refetch()}>{t("Retry")}</Button></div>}
            {history.data?.messages.length === 0 && <p>{t("No conversation saved")}</p>}
            {history.data && <ol className="space-y-3">{history.data.messages.map((message, index) => <li key={index} className="rounded-md border p-3">
              <p className="text-sm font-semibold">{t(message.role === "user" ? "Customer" : "Assistant")}</p>
              <Markdown content={message.text} className="min-w-0 overflow-x-auto break-words" />
            </li>)}</ol>}
          </CardContent>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  </Card>;
}
