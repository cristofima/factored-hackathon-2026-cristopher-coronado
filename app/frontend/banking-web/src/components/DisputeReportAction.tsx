import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { canReportDispute } from "@/common/financial";
import type { FinancialTransaction } from "@/api/financialClient";
import type { useDisputeEligibility } from "@/hooks/useDisputeEligibility";
import ReportDisputeDialog from "@/components/ReportDisputeDialog";

export default function DisputeReportAction({ record, eligibility }: Readonly<{
  record: FinancialTransaction;
  eligibility: ReturnType<typeof useDisputeEligibility>;
}>) {
  const { t } = useTranslation();
  if (eligibility.status !== "ready") return null;
  const existing = eligibility.activeCases.get(record.id);
  if (existing) {
    return <Link to={`/support-cases/${existing.caseId}`} className="text-primary hover:underline">
      {t("View existing dispute")}
    </Link>;
  }
  return canReportDispute(record) ? <ReportDisputeDialog
    key={`${eligibility.scope}-${record.id}`}
    transactionId={record.id}
    onCasesChanged={eligibility.refresh}
  /> : null;
}
