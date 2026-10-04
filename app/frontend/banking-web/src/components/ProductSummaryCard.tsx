import { CreditCard, Landmark } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { AccountSummary, CardSummary } from "@/api/authClient";
import { maskedCardNumber, productPath, productStatusKey } from "@/common/products";

import { formatProductAmount } from "@/common/productAmount";

type Props = Readonly<{
  product: AccountSummary | CardSummary;
  kind: "account" | "card";
  headingId: string;
  linked?: boolean;
}>;

export default function ProductSummaryCard({ product, kind, headingId, linked = false }: Props) {
  const { t, i18n } = useTranslation();
  const card = kind === "card" ? product as CardSummary : undefined;
  const Icon = card ? CreditCard : Landmark;
  const number = card ? maskedCardNumber(product.number) : product.number;
  const amount = (value: string | null | undefined) => value == null ? t("Not available") : formatProductAmount(value, i18n?.resolvedLanguage ?? i18n?.language ?? "en");
  return (
    <article aria-labelledby={headingId} className={`relative overflow-hidden rounded-xl border bg-card text-card-foreground shadow-sm ${linked ? "hover:bg-muted/20" : ""}`}>
      <header className="flex items-start justify-between gap-4 border-b bg-muted/30 p-5 sm:p-6">
        <div className="flex min-w-0 gap-3">
          <span className="rounded-lg bg-primary/10 p-2.5 text-primary"><Icon className="h-5 w-5" aria-hidden="true" /></span>
          <div className="min-w-0 space-y-2">
            <h2 id={headingId} className="text-base font-semibold">
              {linked ? <Link to={productPath(product.product_id)} className="after:absolute after:inset-0 focus-visible:outline-none after:focus-visible:ring-2 after:focus-visible:ring-inset after:focus-visible:ring-ring">{t(product.type)}<span className="sr-only"> · {number || t("Number unavailable")} · {t("View product movements")}</span></Link> : t(product.type)}
            </h2>
            <p className="break-all font-mono text-lg tabular-nums">{number || t("Number unavailable")}</p>
          </div>
        </div>
        <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${product.status?.toLowerCase() === "active" ? "bg-emerald-50 text-emerald-800" : "bg-muted text-muted-foreground"}`}>{t(productStatusKey(product.status))}</span>
      </header>
      <dl className="grid grid-cols-2 gap-5 p-5 sm:p-6">
        <div className="col-span-2 space-y-1">
          <dt className="text-sm text-muted-foreground">{t("Stored balance")}</dt>
          <dd className="break-words text-3xl font-semibold tracking-tight tabular-nums"><span className="mr-2 text-sm font-medium text-muted-foreground">{product.currency}</span>{amount(product.balance)}</dd>
        </div>
        {card && product.type === "Credit Card" && <div className="col-span-2 space-y-1 border-t pt-4">
          <dt className="text-sm text-muted-foreground">{t("Credit limit")}</dt>
          <dd className="break-words text-base font-medium tabular-nums">{card.credit_limit !== null && <span className="mr-2 text-sm text-muted-foreground">{product.currency}</span>}{amount(card.credit_limit)}</dd>
        </div>}
        <div className="space-y-1"><dt className="text-xs text-muted-foreground">{t("Opened")}</dt><dd className="text-sm tabular-nums">{product.opened ?? t("Not available")}</dd></div>
        {card && <div className="space-y-1"><dt className="text-xs text-muted-foreground">{t("Expires")}</dt><dd className="text-sm tabular-nums">{card.expires ?? t("Not available")}</dd></div>}
      </dl>
    </article>
  );
}
