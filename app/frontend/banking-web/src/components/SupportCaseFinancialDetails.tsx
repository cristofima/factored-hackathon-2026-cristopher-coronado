import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useProductCatalog } from "@/hooks/useProductCatalog";
import type { SupportCase } from "@/models/SupportCase";
import { formatProductAmount } from "@/common/productAmount";
import { disputeProtectionStatus } from "@/common/disputePresentation";
import { maskedCardNumber } from "@/common/products";
import { formatDateTime } from "@/common/dateTime";
import { useAuth } from "@/context/AuthContext";

export default function SupportCaseFinancialDetails({ supportCase }: { supportCase: SupportCase }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const catalog = useProductCatalog(JSON.stringify([supportCase.caseId, supportCase.status, supportCase.financialEffectsStatus, supportCase.effects?.movementId]));
  const effects = supportCase.effects;
  const protection = supportCase.cardProtection;
  const rationale = supportCase.rationale ?? supportCase.resolutionNotes;
  return <Card>
    <CardHeader><CardTitle className="text-base">{t("Financial movement")}</CardTitle></CardHeader>
    <CardContent className="min-w-0 space-y-3 text-sm [overflow-wrap:anywhere]">
      <p>{t("Original transaction")}: <span className="font-mono">{supportCase.transactionId}</span></p>
      {supportCase.status === "PENDING_EFFECTS" && <p>{t("Restitution is pending. No completed credit or balance change is confirmed.")}</p>}
      {supportCase.status === "RESOLVED_INVALID" && <p>{t("Invalid verdict recorded. No restitution was posted for this case.")}</p>}
      {supportCase.verdict && <p>{t("Final verdict")}: {t(supportCase.verdict === "valid" ? "Valid dispute" : "Invalid dispute")}</p>}
      {supportCase.status === "PENDING_EFFECTS" && <p>{t(`operator.effects.${supportCase.effectCode ?? "PENDING"}`, { keySeparator: ".", defaultValue: t("Financial execution is pending") })}</p>}
      {effects && <div role="status" className="space-y-1">
        <p>{t("Full original-currency restitution posted. Credit-card adjustments reduce debt.")}</p>
        <p>{t("This recorded application movement does not confirm external settlement.")}</p>
        <p>{t("Financial movement")}: <span className="font-mono">{effects.movementId}</span></p>
        <p>{t("Destination product")}: {effects.destinationProductId}</p>
        <p>{t("Amount")}: {formatProductAmount(effects.amount, user?.locale ?? "en")} {effects.currency}</p>
        <p>{t("Recorded balance adjustment")}: {formatProductAmount(effects.balanceDelta, user?.locale ?? "en")} {effects.currency}</p>
        <p>{t("Executed")}: {formatDateTime(effects.executedAt, user?.locale, "date-time")}</p>
      </div>}
      {rationale && <p className="whitespace-pre-wrap">{t("Rationale")}: {rationale}</p>}
      {protection && <div className="space-y-1">
        <p>{t("Action")}: {t(protection.blocked ? "Block in application" : "Unblock in application")}</p>
        <p>{t("Recorded prior status")}: {disputeProtectionStatus(protection.priorStatus, t)}</p>
        <p className="whitespace-pre-wrap">{t("Rationale")}: {protection.rationale}</p>
        <p>{t("Support case")}: {protection.caseId} · {formatDateTime(protection.updatedAt, user?.locale, "date-time")}</p>
      </div>}
      <p>{t("Card protection is a separate audited action. It only affects this application, not the processor or card network.")}</p>
      <h3 className="font-semibold">{t("Current balances")}</h3>
      {catalog.loading && <output className="block">{t("Loading products...")}</output>}
      {catalog.error && <p role="alert">{t(catalog.error)}</p>}
      {!catalog.loading && !catalog.error && <>
        {catalog.accounts.length + catalog.cards.length === 0 && <p>{t("Balances are unavailable")}</p>}
        <ul className="space-y-1">{[
                  ...catalog.accounts.map(product => ({ ...product, displayNumber: product.number })),
                  ...catalog.cards.map(product => ({ ...product, displayNumber: maskedCardNumber(product.number) })),
                ].map(product => <li key={product.product_id}>
                  {product.displayNumber ?? t("Unavailable")}: {product.balance == null ? t("Unavailable") : formatProductAmount(product.balance, user?.locale ?? "en")} {product.currency}
                </li>)}</ul>
      </>}
      <p>{t("This only reloads balances; it does not issue a refund or change any balance.")}</p>
      <Button variant="outline" onClick={catalog.retry}>{t("Reload displayed balances")}</Button>
    </CardContent>
  </Card>;
}
