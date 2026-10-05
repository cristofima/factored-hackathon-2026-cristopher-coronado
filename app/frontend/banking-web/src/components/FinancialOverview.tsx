import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { useProductCatalog } from "@/hooks/useProductCatalog";
import { maskedCardNumber, resolveProduct } from "@/common/products";
import { FinancialTransaction, getTransactions } from "@/api/financialClient";
import { errorTranslationKey } from "@/api/errors";
import {
  calendarDate,
  decimalString,
  summarizeTransactions,
} from "@/common/financial";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import ProductSummaryCard from "@/components/ProductSummaryCard";
import { formatProductAmount } from "@/common/productAmount";
import DisputeReportAction from "@/components/DisputeReportAction";
import { useDisputeEligibility } from "@/hooks/useDisputeEligibility";
import { useTranslation } from "react-i18next";

export default function FinancialOverview({ productId: requestedProductId }: Readonly<{ productId?: string }>) {
  const { t, i18n } = useTranslation();
  const formatAmount = (value: string) => formatProductAmount(value, i18n?.resolvedLanguage ?? i18n?.language ?? "en");
  const [params, setParams] = useSearchParams();
  const { accounts, cards, scope, loading: accountsLoading, error: accountsError, retry } = useProductCatalog();
  const [storedRecords, setRecords] = useState<FinancialTransaction[]>([]);
  const [recordsScope, setRecordsScope] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [page, setPage] = useState(1);
  const [start, setStart] = useState(() => {
    if (params.get("start")) return params.get("start")!;
    const value = new Date();
    value.setDate(value.getDate() - 29);
    return calendarDate(value);
  });
  const [end, setEnd] = useState(
    () => params.get("end") ?? calendarDate(new Date()),
  );

  const selected = resolveProduct(accounts, cards, requestedProductId);
  const account = selected?.kind === "account" ? selected.item : undefined;
  const card = selected?.kind === "card" ? selected.item : undefined;
  const product = selected?.item;
  const selectedId = product?.product_id ?? "";
  const eligibility = useDisputeEligibility(Boolean(card));
  const displayNumber = card ? maskedCardNumber(card.number) ?? "" : account?.number ?? "";
  const productId = card?.product_id;
  const historyScope = JSON.stringify([scope, selectedId, start, end]);
  const records = recordsScope === historyScope && product ? storedRecords : [];

  useEffect(() => {
    const controller = new AbortController();
    setRecords([]);
    setPage(1);
    setError(null);
    setLoading(false);
    if (!selectedId || (!displayNumber && productId === undefined)) return () => controller.abort();
    if (!start || !end || start > end) {
      setError("Choose a valid inclusive start and end date.");
      return () => controller.abort();
    }
    setLoading(true);
    getTransactions(displayNumber, start, end, controller.signal, productId)
      .then((items) => {
        summarizeTransactions(items);
        if (!controller.signal.aborted) {
          setRecords(items);
          setRecordsScope(historyScope);
        }
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setError(errorTranslationKey(cause, "Transactions are unavailable"));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [selectedId, displayNumber, productId, start, end, historyScope, attempt]);
  const summary = summarizeTransactions(records);
  const changeWindow = (update: () => void) => {
    setRecords([]);
    setLoading(true);
    update();
  };
  const pageCount = Math.max(1, Math.ceil(records.length / 25));
  const currentPage = Math.min(page, pageCount);
  const visible = records.slice((currentPage - 1) * 25, currentPage * 25);
  const errorKey = error ?? "Transactions are unavailable";
  return (
    <section className="mx-auto max-w-7xl p-4 sm:p-6 space-y-6 animate-fade-in">
      <h1 className="text-2xl font-bold">
        {t("Product movements")}
      </h1>
      <Link to="/" className="text-sm text-primary hover:underline">{t("My products")}</Link>
      {card && eligibility.status === "loading" && (
        <output>{t("Checking active disputes...")}</output>
      )}
      {card && eligibility.status === "error" && (
        <div role="alert">
          <p>{t("Dispute eligibility unavailable. Reporting is disabled.")}</p>
          <Button variant="outline" onClick={eligibility.refresh}>{t("Retry")}</Button>
        </div>
      )}
      {accountsLoading && <output>{t("Loading products...")}</output>}
      {accountsError && <div role="alert">{t(accountsError)}</div>}
      {(accountsError || error) && (
        <Button
          variant="outline"
          onClick={() =>
            accountsError
              ? retry()
              : setAttempt((value) => value + 1)
          }
        >
          <RefreshCw className="mr-2 h-4 w-4" aria-hidden="true" /> {t("Retry")}
        </Button>
      )}
      {!accountsLoading && !accountsError && !accounts.length && !cards.length && (
        <output>{t("No products are registered for this customer.")}</output>
      )}
      {!accountsLoading && !accountsError && !product && (
        <output>{t("Selected product is unavailable.")}</output>
      )}
      {product && selected && <div className="max-w-2xl"><ProductSummaryCard product={product} kind={selected.kind} headingId="selected-product" /></div>}
      {product && (
        <div className="flex flex-wrap gap-4 items-end rounded-xl border bg-card p-5">
          <h2 className="w-full text-lg font-semibold">{t("Filter movements")}</h2>
          <label className="space-y-2 text-sm font-medium">
            <span className="block">{t("Start date")}</span>
            <input
              aria-label={t("Start date")}
              type="date"
              value={start}
              onChange={(event) =>
                changeWindow(() => {
                  setStart(event.target.value);
                  setParams({ start: event.target.value, end }, { replace: true });
                })
              }
              className="block h-10 rounded-md border bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </label>
          <label className="space-y-2 text-sm font-medium">
            <span className="block">{t("End date")}</span>
            <input
              aria-label={t("End date")}
              type="date"
              value={end}
              onChange={(event) =>
                changeWindow(() => {
                  setEnd(event.target.value);
                  setParams({ start, end: event.target.value }, { replace: true });
                })
              }
              className="block h-10 rounded-md border bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </label>
        </div>
      )}
      {loading && (
        <output>{t("Loading the complete transaction window...")}</output>
      )}
      {error && <div role="alert">{t(errorKey)}</div>}
      {product && !loading && !error && (
        <>
          <p className="text-sm text-muted-foreground">{t("Movement window", { count: records.length, start, end })}</p>
          {(
            <>
              <details className="rounded-lg border bg-muted/20 px-4 py-3 text-sm text-muted-foreground">
                <summary className="cursor-pointer font-medium text-foreground">{t("About these totals")}</summary>
                <div className="mt-3 space-y-2">
                  <p>{t("Window context", { count: records.length, start, end })}</p>
                  <p>{t("Movement policy")}</p>
                  <p>{t("Excluded records", { count: summary.excluded })}</p>
                </div>
              </details>
              <div className="grid gap-4 lg:grid-cols-2">
                {[...summary.currencies].map(([currency, totals]) => (
                  <Card key={currency}>
                    <CardHeader>
                      <CardTitle>
                        {t("{{currency}} movements", { currency })}
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="grid gap-4 sm:grid-cols-3 break-words tabular-nums">
                      <p>
                        {t("Inflow")}: {currency} {formatAmount(decimalString(totals.inflow))}
                      </p>
                      <p>
                        {t("Outflow")}: {currency}{" "}
                        {formatAmount(decimalString(totals.outflow))}
                      </p>
                      <p>
                        {t("Net movement")}: {currency}{" "}
                        {formatAmount(decimalString(totals.inflow - totals.outflow))}
                      </p>
                      <p>{t("Classified records", { count: totals.count })}</p>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </>
          )}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                {t("Transactions in Selected Window")}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {!records.length ? (
                <output className="block py-6 text-sm text-muted-foreground">
                  {t("Empty window")}
                </output>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-left">
                    <thead className="bg-muted/50 text-muted-foreground">
                      <tr>
                        {[
                          "Date",
                          "Merchant",
                          "Type / category",
                          "Channel",
                          "Status",
                          "Amount",
                        ].map((heading) => (
                          <th key={heading} className="p-3 whitespace-nowrap">
                            {t(heading)}
                          </th>
                        ))}
                        {card && <th className="p-3 whitespace-nowrap">{t("Dispute actions")}</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {visible.map((record) => (
                        <tr
                          key={record.id}
                          className="border-t hover:bg-muted/30"
                        >
                          <td className="p-3 whitespace-nowrap">
                            {record.date.slice(0, 10)}
                          </td>
                          <td className="p-3">
                            {record.merchant ?? t("Not available")}
                            <div className="text-sm text-muted-foreground">
                              {t("Country")}: {record.country ?? t("Not available")} · {t("City")}: {record.city ?? t("Not available")}
                            </div>
                            {record.supportCaseId && <div className="text-sm">
                              <Link to={`/support-cases/${encodeURIComponent(record.supportCaseId)}`} className="text-primary hover:underline">
                                {t("Support case")} {record.supportCaseId}
                              </Link>
                            </div>}
                            {record.originalTransactionId && <div className="text-sm text-muted-foreground">
                              {t("Original transaction")} {record.originalTransactionId}
                            </div>}
                          </td>
                          <td className="p-3">
                            {record.type === null
                              ? t("Not available")
                              : t(`transactions.types.${record.type}`, {
                                  keySeparator: ".",
                                  defaultValue: record.type,
                                })}{" "}
                            /{" "}
                            {record.category === null
                              ? t("Not available")
                              : t(
                                  `transactions.categories.${record.category}`,
                                  {
                                    keySeparator: ".",
                                    defaultValue: record.category,
                                  },
                                )}
                          </td>
                          <td className="p-3">
                            {record.channel ?? t("Not available")}
                          </td>
                          <td className="p-3">
                            {record.status === null
                              ? t("Not available")
                              : t(`transactions.statuses.${record.status}`, {
                                  keySeparator: ".",
                                  defaultValue: record.status,
                                })}
                          </td>
                          <td className="p-3 whitespace-nowrap text-right font-medium tabular-nums">
                            {record.currency} {formatAmount(record.amount)}
                          </td>
                          {card && (
                            <td className="p-3 whitespace-nowrap">
                              <DisputeReportAction record={record} eligibility={eligibility} />
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {records.length > 25 && (
                <nav aria-label={t("Movement pagination")} className="mt-4 flex items-center justify-between gap-3">
                  <Button variant="outline" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}>{t("Previous")}</Button>
                  <span>{t("Page {{page}} of {{count}}", { page: currentPage, count: pageCount })}</span>
                  <Button variant="outline" disabled={currentPage === pageCount} onClick={() => setPage(currentPage + 1)}>{t("Next")}</Button>
                </nav>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </section>
  );
}
