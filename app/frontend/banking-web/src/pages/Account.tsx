import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { AccountSummary, getAccounts } from "@/api/authClient";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";

const maskNumber = (number: string) => `**** ${number.slice(-4)}`;

export default function Account() {
  const { user } = useAuth();
  const [accounts, setAccounts] = useState<AccountSummary[]>([]);
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
          setSelectedId(result[0]?.id ?? "");
        }
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setError(
            cause instanceof Error ? cause.message : "Accounts are unavailable",
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [user?.id, attempt]);

  const account = accounts.find((item) => item.id === selectedId);
  const opened = account?.opened
    ? new Intl.DateTimeFormat(user?.locale || "en", {
        dateStyle: "long",
      }).format(new Date(`${account.opened}T00:00:00`))
    : "Not available";

  return (
    <div className="p-6 max-w-6xl space-y-6">
      <h1 className="text-2xl font-bold text-foreground">Account Overview</h1>
      <p className="max-w-3xl text-sm text-muted-foreground">
        Access your essential account details, codes, agreements, and policy
        information. For any questions, please contact{" "}
        <a
          href="mailto:support@bankwise.com"
          className="text-blue-600 underline"
        >
          support@bankwise.com
        </a>
        .
      </p>
      {loading && <output className="block">Loading accounts...</output>}
      {error && (
        <div role="alert" className="flex flex-wrap items-center gap-3">
          <p>{error}</p>
          <Button
            variant="outline"
            onClick={() => setAttempt((value) => value + 1)}
          >
            <RefreshCw className="mr-2 h-4 w-4" />
            Retry
          </Button>
        </div>
      )}
      {!loading && !error && accounts.length === 0 && (
        <output className="block">
          No bank accounts are registered for this customer.
        </output>
      )}
      {accounts.length > 1 && (
        <div className="space-y-2">
          <label
            htmlFor="account-selector"
            className="block text-sm font-medium"
          >
            Account
          </label>
          <select
            id="account-selector"
            value={selectedId}
            onChange={(event) => setSelectedId(event.target.value)}
            className="h-10 w-full max-w-xl rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {accounts.map((item) => (
              <option key={item.id} value={item.id}>
                {item.type} - {item.number ? maskNumber(item.number) : item.id}{" "}
                ({item.currency})
              </option>
            ))}
          </select>
        </div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5 items-start">
        {/* General Information */}
        <Card className="p-5 shadow-sm md:col-start-1">
          <section>
            <h2 className="text-base font-semibold mb-4">
              General Information
            </h2>
            <dl className="space-y-3 text-sm">
              <div className="grid grid-cols-[8rem_minmax(0,1fr)] gap-3">
                <dt className="text-muted-foreground">Account Holder</dt>
                <dd className="break-words font-medium">
                  {user?.name || user?.email || "Not available"}
                </dd>
              </div>
              {account && (
                <>
                  <div className="grid grid-cols-[8rem_minmax(0,1fr)] gap-3">
                    <dt className="text-muted-foreground">Account Type</dt>
                    <dd>{account.type}</dd>
                  </div>
                  <div className="grid grid-cols-[8rem_minmax(0,1fr)] gap-3">
                    <dt className="text-muted-foreground">Status</dt>
                    <dd>{account.status || "Not available"}</dd>
                  </div>
                  <div className="grid grid-cols-[8rem_minmax(0,1fr)] gap-3">
                    <dt className="text-muted-foreground">Opened</dt>
                    <dd>{opened}</dd>
                  </div>
                  <div className="grid grid-cols-[8rem_minmax(0,1fr)] gap-3">
                    <dt className="text-muted-foreground">Currency</dt>
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
              <h2 className="text-base font-semibold mb-4">Account Codes</h2>
              <dl className="space-y-2 text-sm">
                <dt className="text-muted-foreground">Account Number</dt>
                <dd className="font-mono break-all">{account.number}</dd>
              </dl>
            </section>
          </Card>
        )}
        {/* Agreements */}
        <Card className="p-5 shadow-sm md:col-start-1 md:row-start-2">
          <section>
            <h2 className="text-base font-semibold mb-4">Agreements</h2>
            <ul className="list-disc ml-5 text-sm space-y-3">
              <li>
                <a href="#" className="text-blue-600 underline font-medium">
                  Terms of Service
                </a>{" "}
                — Outlines your rights and responsibilities as an account
                holder.
              </li>
              <li>
                <a href="#" className="text-blue-600 underline font-medium">
                  Electronic Communications Agreement
                </a>{" "}
                — Details how we deliver important information electronically.
              </li>
              <li>
                <a href="#" className="text-blue-600 underline font-medium">
                  Fee Schedule
                </a>{" "}
                — Provides information on account-related fees.
              </li>
            </ul>
          </section>
        </Card>
        {/* Policy */}
        <Card className="p-5 shadow-sm md:col-start-2 md:row-start-2">
          <section>
            <h2 className="text-base font-semibold mb-4">
              Privacy & Security Policy
            </h2>
            <div className="text-sm leading-relaxed">
              <p className="mb-2">
                Your privacy and security are our top priorities. We use
                industry-leading encryption and security practices to protect
                your data and financial information.
              </p>
              <p className="mb-2">
                We do <span className="font-semibold">not</span> share your
                information with third parties without your explicit consent.
                You can review our full policy below:
              </p>
              <a href="#" className="text-blue-600 underline font-medium">
                View Privacy Policy
              </a>
            </div>
          </section>
        </Card>
      </div>
    </div>
  );
}
