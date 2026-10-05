import { useTranslation } from "react-i18next";
import type { SupportCase, SupportCaseEvent } from "@/models/SupportCase";

export default function SupportCaseIntakeReceipt({ supportCase, events }: { supportCase: SupportCase; events: SupportCaseEvent[] }) {
  const { t } = useTranslation();
  const consent = events.filter(event => ["APPROVAL_REQUESTED", "APPROVAL_GRANTED", "APPROVAL_DECLINED"].includes(event.eventType))
    .sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt))[0];
  return <div className="space-y-2" role="status">
    <p>{t("Support case")}: <span className="font-mono">{supportCase.caseId}</span></p>
    <p>{t("Original transaction")}: <span className="font-mono">{supportCase.transactionId}</span></p>
    <p>{t("Customer statement")}: <span className="whitespace-pre-wrap">{supportCase.reason}</span></p>
    <p>{t(`support-cases.status.${supportCase.status}`, { keySeparator: ".", defaultValue: t("Unavailable") })}</p>
    <p>{t("Intake recorded; this is not consent to proceed.")}</p>
    <p>{consent ? t(`support-cases.messages.${consent.eventType}`, { keySeparator: ".", defaultValue: t("Consent record unavailable") }) : t("Consent record unavailable")}</p>
  </div>;
}
