import { useTranslation } from "react-i18next";
import { formatDateTime } from "@/common/dateTime";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { supportCaseEventMessageKey, type SupportCaseEvent } from "@/models/SupportCase";

export default function SupportCaseTimeline({ events, transactionId, perspective = "customer" }: {
  events: SupportCaseEvent[];
  transactionId: string;
  perspective?: "customer" | "operator";
}) {
  const { t, i18n } = useTranslation();
  const translate = (key: string, fallback: string) => {
    const customerText = t(key, { keySeparator: ".", transactionId, defaultValue: fallback });
    return perspective === "operator"
      ? t(key.replace("support-cases.", "support-cases.operator."), {
        keySeparator: ".", transactionId, defaultValue: customerText,
      })
      : customerText;
  };
  return <Card>
    <CardHeader><CardTitle className="text-base">{t("Timeline")}</CardTitle></CardHeader>
    <CardContent>
      <ol className="space-y-3">
        {events.map((event, index) => <li key={`${event.eventType}-${index}`} className="text-sm border-l-2 pl-3">
          <p className="font-medium">{translate(`support-cases.events.${event.eventType}`, event.eventType)}</p>
          {(event.displayMessage ?? event.message) && <p className="text-muted-foreground">
            {translate(supportCaseEventMessageKey(event), event.displayMessage ?? event.message ?? t("Not available"))}
          </p>}
          <p className="text-xs text-muted-foreground"><time dateTime={event.createdAt}>{formatDateTime(event.createdAt, i18n.language, "date-time-seconds")}</time></p>
        </li>)}
      </ol>
    </CardContent>
  </Card>;
}
