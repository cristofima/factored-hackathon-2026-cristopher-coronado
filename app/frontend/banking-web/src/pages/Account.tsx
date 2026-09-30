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
    <div className="p-8 max-w-6xl mx-auto space-y-8">
      <h1 className="text-3xl font-bold mb-2 text-slate-900">
        Account Overview
      </h1>
      <p className="text-slate-600 mb-6 text-base">
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
            className="w-full max-w-xl rounded-md border border-input bg-background p-3"
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
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* General Information */}
        <Card className="p-8 shadow-xl border border-slate-200 flex-1">
          <section>
            <h2 className="text-xl font-semibold mb-2 text-slate-800 flex items-center gap-2">
              General Information
            </h2>
            <div className="text-slate-700 text-base leading-relaxed">
              <div className="mb-2 break-words">
                <span className="font-medium">Account Holder:</span>{" "}
                {user?.name || user?.email || "Not available"}
              </div>
              {account && (
                <>
                  <div className="mb-2">
                    <span className="font-medium">Account Type:</span>{" "}
                    {account.type}
                  </div>
                  <div className="mb-2">
                    <span className="font-medium">Status:</span>{" "}
                    {account.status || "Not available"}
                  </div>
                  <div className="mb-2">
                    <span className="font-medium">Opened:</span> {opened}
                  </div>
                  <div>
                    <span className="font-medium">Currency:</span>{" "}
                    {account.currency}
                  </div>
                </>
              )}
            </div>
          </section>
        </Card>
        {/* Account Codes */}
        {account?.number && (
          <Card className="p-8 shadow-xl border border-slate-200 flex-1">
            <section>
              <h2 className="text-xl font-semibold mb-2 text-slate-800 flex items-center gap-2">
                Account Codes
              </h2>
              <div className="grid grid-cols-1 gap-4 text-slate-700">
                <div>
                  <span className="font-medium">Account Number:</span>{" "}
                  <span className="font-mono break-all">{account.number}</span>
                </div>
              </div>
            </section>
          </Card>
        )}
        {/* Agreements */}
        <Card className="p-8 shadow-xl border border-slate-200 flex-1">
          <section>
            <h2 className="text-xl font-semibold mb-2 text-slate-800 flex items-center gap-2">
              Agreements
            </h2>
            <ul className="list-disc ml-6 text-slate-700 space-y-2">
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
        <Card className="p-8 shadow-xl border border-slate-200 flex-1">
          <section>
            <h2 className="text-xl font-semibold mb-2 text-slate-800 flex items-center gap-2">
              Privacy & Security Policy
            </h2>
            <div className="text-slate-700 text-base leading-relaxed">
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
