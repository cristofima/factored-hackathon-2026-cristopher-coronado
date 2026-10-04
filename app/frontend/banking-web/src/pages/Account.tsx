import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { productPath, productStatusKey } from "@/common/products";
import { Card } from "@/components/ui/card";
import { AccountSummary, getAccounts } from "@/api/authClient";
import { errorTranslationKey } from "@/api/errors";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";

export default function Account() {
  const { t, i18n } = useTranslation();
  const { user, sessionKey } = useAuth();
  const scope = JSON.stringify([user?.id, sessionKey]);
  const [storedScope, setStoredScope] = useState("");
  const [storedAccounts, setAccounts] = useState<AccountSummary[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setAccounts([]);
    setSelectedId("");
    getAccounts(controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) {
          setAccounts(result);
          setStoredScope(scope);
          setSelectedId(result.find((item) => item.number)?.number ?? "");
        }
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setError(errorTranslationKey(cause, "Accounts are unavailable"));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [scope, attempt]);

  const accounts = storedScope === scope ? storedAccounts : [];
  const account = accounts.find((item) => item.number === selectedId);
  const opened = account?.opened
    ? new Intl.DateTimeFormat(i18n.language, {
        dateStyle: "long",
      }).format(new Date(`${account.opened}T00:00:00`))
    : t("Not available");

  return (
    <div className="p-6 max-w-6xl space-y-6">
      <h1 className="text-2xl font-bold text-foreground">
        {t("Account Overview")}
      </h1>
      <p className="max-w-3xl text-sm text-muted-foreground">
        {t("Account help")}{" "}
        <a
          href="mailto:support@bankwise.com"
          className="text-blue-600 underline"
        >
          support@bankwise.com
        </a>
        .
      </p>
      {loading && <output className="block">{t("Loading accounts...")}</output>}
      {error && (
        <div role="alert" className="flex flex-wrap items-center gap-3">
          <p>{t(error)}</p>
          <Button
            variant="outline"
            onClick={() => setAttempt((value) => value + 1)}
          >
            <RefreshCw className="mr-2 h-4 w-4" />
            {t("Retry")}
          </Button>
        </div>
      )}
      {!loading && !error && accounts.length === 0 && (
        <output className="block">
          {t("No bank accounts are registered for this customer.")}
        </output>
      )}
      {accounts.length > 1 && (
        <div className="space-y-2">
          <label
            htmlFor="account-selector"
            className="block text-sm font-medium"
          >
            {t("Account")}
          </label>
          <select
            id="account-selector"
            value={selectedId}
            onChange={(event) => setSelectedId(event.target.value)}
            className="h-10 w-full max-w-xl rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {accounts.map((item, index) => (
              <option
                key={item.number ?? `unavailable-${index}`}
                value={item.number ?? ""}
                disabled={!item.number}
              >
                {t(item.type)} - {item.number ?? t("Number unavailable")} (
                {item.currency})
              </option>
            ))}
          </select>
        </div>
      )}
      {account?.product_id && <Link to={productPath(account.product_id)} className="inline-block text-sm text-primary hover:underline">{t("View product movements")}</Link>}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5 items-start">
        {/* General Information */}
        <Card className="p-5 shadow-sm md:col-start-1">
          <section>
            <h2 className="text-base font-semibold mb-4">
              {t("General Information")}
            </h2>
            <dl className="space-y-3 text-sm">
              <div className="grid grid-cols-[8rem_minmax(0,1fr)] gap-3">
                <dt className="text-muted-foreground">{t("Account Holder")}</dt>
                <dd className="break-words font-medium">
                  {user?.name || user?.email || t("Not available")}
                </dd>
              </div>
              {account && (
                <>
                  <div className="grid grid-cols-[8rem_minmax(0,1fr)] gap-3">
                    <dt className="text-muted-foreground">
                      {t("Account Type")}
                    </dt>
                    <dd>{t(account.type)}</dd>
                  </div>
                  <div className="grid grid-cols-[8rem_minmax(0,1fr)] gap-3">
                    <dt className="text-muted-foreground">{t("Status")}</dt>
                    <dd>{t(productStatusKey(account.status))}</dd>
                  </div>
                  <div className="grid grid-cols-[8rem_minmax(0,1fr)] gap-3">
                    <dt className="text-muted-foreground">{t("Opened")}</dt>
                    <dd>{opened}</dd>
                  </div>
                  <div className="grid grid-cols-[8rem_minmax(0,1fr)] gap-3">
                    <dt className="text-muted-foreground">{t("Currency")}</dt>
                    <dd>{account.currency}</dd>
                  </div>
                </>
              )}
            </dl>
          </section>
        </Card>
        {/* Account Codes */}
        {account?.number && (
          <Card className="p-5 shadow-sm md:col-start-2 md:row-start-1">
            <section>
              <h2 className="text-base font-semibold mb-4">
                {t("Account Codes")}
              </h2>
              <dl className="space-y-2 text-sm">
                <dt className="text-muted-foreground">{t("Account Number")}</dt>
                <dd className="font-mono break-all">{account.number}</dd>
              </dl>
            </section>
          </Card>
        )}
        {/* Agreements */}
        <Card className="p-5 shadow-sm md:col-start-1 md:row-start-2">
          <section>
            <h2 className="text-base font-semibold mb-4">{t("Agreements")}</h2>
            <ul className="list-disc ml-5 text-sm space-y-3">
              <li>
                <a href="#" className="text-blue-600 underline font-medium">
                  {t("Terms of Service")}
                </a>{" "}
                {t("Rights description")}
              </li>
              <li>
                <a href="#" className="text-blue-600 underline font-medium">
                  {t("Electronic Communications Agreement")}
                </a>{" "}
                {t("Communications description")}
              </li>
              <li>
                <a href="#" className="text-blue-600 underline font-medium">
                  {t("Fee Schedule")}
                </a>{" "}
                {t("Fees description")}
              </li>
            </ul>
          </section>
        </Card>
        {/* Policy */}
        <Card className="p-5 shadow-sm md:col-start-2 md:row-start-2">
          <section>
            <h2 className="text-base font-semibold mb-4">
              {t("Privacy & Security Policy")}
            </h2>
            <div className="text-sm leading-relaxed">
              <p className="mb-2">{t("Privacy description")}</p>
              <p className="mb-2">{t("Consent description")}</p>
              <a href="#" className="text-blue-600 underline font-medium">
                {t("View Privacy Policy")}
              </a>
            </div>
          </section>
        </Card>
      </div>
    </div>
  );
}
