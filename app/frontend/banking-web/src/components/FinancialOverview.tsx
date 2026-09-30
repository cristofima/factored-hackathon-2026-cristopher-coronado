import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight, RefreshCw } from "lucide-react";
import { AccountSummary, getAccounts } from "@/api/authClient";
import { FinancialTransaction, getTransactions } from "@/api/financialClient";
import {
  calendarDate,
  decimalString,
  summarizeTransactions,
} from "@/common/financial";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function FinancialOverview({
  analytics = false,
}: Readonly<{ analytics?: boolean }>) {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const requestedId = params.get("account") ?? "";
  const [accounts, setAccounts] = useState<AccountSummary[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [accountsLoading, setAccountsLoading] = useState(true);
  const [accountsError, setAccountsError] = useState<string | null>(null);
  const [records, setRecords] = useState<FinancialTransaction[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [accountsAttempt, setAccountsAttempt] = useState(0);
  const [start, setStart] = useState(() => {
    if (params.get("start")) return params.get("start")!;
    const value = new Date();
    value.setDate(value.getDate() - 29);
    return calendarDate(value);
  });
  const [end, setEnd] = useState(
    () => params.get("end") ?? calendarDate(new Date()),
  );

  useEffect(() => {
    const controller = new AbortController();
    setAccounts([]);
    setSelectedId("");
    setRecords([]);
    setAccountsLoading(true);
    setAccountsError(null);
    getAccounts(controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) {
          setAccounts(items);
        }
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setAccountsError(
            cause instanceof Error ? cause.message : "Accounts are unavailable",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setAccountsLoading(false);
      });
    return () => controller.abort();
  }, [user?.id, accountsAttempt]);

  useEffect(() => {
    setSelectedId(
      accounts.find((item) => item.number === requestedId)?.number ??
        accounts.find((item) => item.number)?.number ??
        "",
    );
  }, [accounts, requestedId]);

  useEffect(() => {
    const controller = new AbortController();
    setRecords([]);
    setError(null);
    setLoading(false);
    if (!selectedId) return () => controller.abort();
    if (!start || !end || start > end) {
      setError("Choose a valid inclusive start and end date.");
      return () => controller.abort();
    }
    setLoading(true);
    getTransactions(selectedId, start, end, controller.signal)
      .then((items) => {
        summarizeTransactions(items);
        if (!controller.signal.aborted) setRecords(items);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setError(
            cause instanceof Error
              ? cause.message
              : "Transactions are unavailable",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [selectedId, start, end, user?.id, attempt]);

  const account = accounts.find((item) => item.number === selectedId);
  const summary = summarizeTransactions(records);
  const changeWindow = (update: () => void) => {
    setRecords([]);
    setLoading(true);
    update();
  };
  const visible = analytics ? records : records.slice(0, 5);
  return (
    <section className="p-6 space-y-6 animate-fade-in">
      <h1 className="text-2xl font-bold">
        {analytics ? "Transaction Analytics" : "Dashboard Overview"}
      </h1>
      <p className="text-sm text-muted-foreground">
        Persisted account data via authenticated BFF. Transaction dates show the
        calendar date returned by the service, without browser timezone
        conversion.
      </p>
      {accountsLoading && <output>Loading accounts...</output>}
      {accountsError && <div role="alert">{accountsError}</div>}
      {(accountsError || error) && (
        <Button
          variant="outline"
          onClick={() =>
            accountsError
              ? setAccountsAttempt((value) => value + 1)
              : setAttempt((value) => value + 1)
          }
        >
          <RefreshCw className="mr-2 h-4 w-4" aria-hidden="true" /> Retry
        </Button>
      )}
      {!accountsLoading && !accountsError && !accounts.length && (
        <output>No bank accounts are registered for this customer.</output>
      )}
      {!!accounts.length && (
        <div className="flex flex-wrap gap-4 items-end border-b pb-5">
          <label className="space-y-2 min-w-0 w-80 text-sm font-medium">
            <span>Account</span>
            <select
              aria-label="Account"
              value={selectedId}
              onChange={(event) =>
                changeWindow(() => {
                  setSelectedId(event.target.value);
                  setParams(
                    { account: event.target.value, start, end },
                    { replace: true },
                  );
                })
              }
              className="block h-10 w-full rounded-md border bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {accounts.map((item, index) => (
                <option
                  key={item.number ?? `unavailable-${index}`}
                  value={item.number ?? ""}
                  disabled={!item.number}
                >
                  {item.type} - {item.number ?? "Number unavailable"} (
                  {item.currency})
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-2 text-sm font-medium">
            <span className="block">Start date</span>
            <input
              aria-label="Start date"
              type="date"
              value={start}
              onChange={(event) =>
                changeWindow(() => setStart(event.target.value))
              }
              className="block h-10 rounded-md border bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </label>
          <label className="space-y-2 text-sm font-medium">
            <span className="block">End date</span>
            <input
              aria-label="End date"
              type="date"
              value={end}
              onChange={(event) =>
                changeWindow(() => setEnd(event.target.value))
              }
              className="block h-10 rounded-md border bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </label>
        </div>
      )}
      {account && (
        <Card className="max-w-xl shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">
              Selected Account Balance
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold break-all tabular-nums mb-2">
              {account.balance === null
                ? "Not available"
                : `${account.currency} ${account.balance}`}
            </p>
            <p className="text-sm text-muted-foreground">
              Stored current balance, not a balance for the selected transaction
              window. Status: {account.status ?? "Not available"}.
            </p>
          </CardContent>
        </Card>
      )}
      {loading && <output>Loading the complete transaction window...</output>}
      {error && <div role="alert">{error}</div>}
      {account && !loading && !error && (
        <>
          <p className="text-sm text-muted-foreground">
            {records.length} transaction records in {start} through {end}{" "}
            (inclusive). All pages loaded for this read; concurrent dataset
            changes may require a refresh.
          </p>
          {analytics && (
            <>
              <p className="text-sm text-muted-foreground">
                Derived movement totals, not income or spending classifications:
                Approved only; Deposit inflow; Payment, Purchase, Transfer and
                Withdrawal outflow. Adjustments, unknown types, other statuses
                and negative amounts are excluded. No mixed-currency totals.
                Transfers follow this dataset policy, not amount signs.
              </p>
              <p>{summary.excluded} records excluded from movement totals.</p>
              <div className="grid gap-4 md:grid-cols-2">
                {[...summary.currencies].map(([currency, totals]) => (
                  <Card key={currency}>
                    <CardHeader>
                      <CardTitle>{currency} movements</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2 break-all">
                      <p>
                        Inflow: {currency} {decimalString(totals.inflow)}
                      </p>
                      <p>
                        Outflow: {currency} {decimalString(totals.outflow)}
                      </p>
                      <p>
                        Net movement: {currency}{" "}
                        {decimalString(totals.inflow - totals.outflow)}
                      </p>
                      <p>{totals.count} classified records</p>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </>
          )}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                {analytics
                  ? "Transactions in Selected Window"
                  : "Recent Transactions in Selected Window"}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {!records.length ? (
                <output className="block py-6 text-sm text-muted-foreground">
                  No transactions in this date window. Try a window within the
                  loaded dataset.
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
                            {heading}
                          </th>
                        ))}
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
                            {record.merchant ?? "Not available"}
                          </td>
                          <td className="p-3">
                            {record.type ?? "Not available"} /{" "}
                            {record.category ?? "Not available"}
                          </td>
                          <td className="p-3">
                            {record.channel ?? "Not available"}
                          </td>
                          <td className="p-3">
                            {record.status ?? "Not available"}
                          </td>
                          <td className="p-3 whitespace-nowrap text-right font-medium tabular-nums">
                            {record.currency} {record.amount}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
          {!analytics && (
            <Link
              to={`/analytics?${new URLSearchParams({ account: selectedId, start, end })}`}
              className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline"
            >
              View full transaction analytics
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          )}
        </>
      )}
      {!analytics && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Unavailable Features</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Credit limits, utilization, historical balance trends,
            beneficiaries, payments, card management and investments have no
            approved financial source in this view. No estimated snapshots or
            mock values are displayed.
          </CardContent>
        </Card>
      )}
    </section>
  );
}
