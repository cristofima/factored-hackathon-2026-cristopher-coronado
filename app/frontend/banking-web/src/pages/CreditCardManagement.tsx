import { useEffect, useState } from "react";
import { CreditCard, RotateCw } from "lucide-react";
import { CardSummary, getCards } from "@/api/authClient";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";

const formatAmount = (amount: string | null): string => {
  if (amount === null) return "Not available";
  const [whole, fraction] = amount.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return fraction === undefined ? grouped : `${grouped}.${fraction}`;
};

const CreditCardManagement = () => {
  const { user } = useAuth();
  const [cards, setCards] = useState<CardSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setCards([]);
    setLoading(true);
    setError(null);
    getCards(controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) setCards(items);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setError(
            cause instanceof Error ? cause.message : "Cards are unavailable",
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [user?.id, attempt]);

  return (
    <section className="p-6 space-y-6">
      <h1 className="flex items-center gap-3 text-2xl font-bold">
        <CreditCard className="h-6 w-6" aria-hidden="true" /> Credit and Debit
        Cards
      </h1>
      {loading && <output>Loading cards...</output>}
      {error && (
        <div className="space-y-3">
          <p role="alert">{error}</p>
          <Button
            variant="outline"
            onClick={() => setAttempt((value) => value + 1)}
          >
            <RotateCw className="mr-2 h-4 w-4" aria-hidden="true" /> Retry
          </Button>
        </div>
      )}
      {!loading && !error && !cards.length && (
        <output>No cards registered.</output>
      )}
      {!!cards.length && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,360px),1fr))] gap-5 max-w-5xl">
          {cards.map((card, index) => (
            <article
              key={index}
              aria-labelledby={`card-${index}`}
              className="overflow-hidden rounded-lg border bg-card text-card-foreground shadow-sm"
            >
              <header className="flex items-start justify-between gap-4 border-b p-5">
                <div className="min-w-0 space-y-2">
                  <h2 id={`card-${index}`} className="text-base font-semibold">
                    {card.type}
                  </h2>
                  <p className="font-mono text-lg tabular-nums">
                    {card.number ?? "Number unavailable"}
                  </p>
                </div>
                <span
                  className={`shrink-0 rounded px-2 py-1 text-xs font-medium ${
                    card.status?.toLowerCase() === "active"
                      ? "bg-emerald-50 text-emerald-800"
                      : "bg-muted text-muted-foreground"
                  }`}
                >
                  {card.status ?? "Status unavailable"}
                </span>
              </header>
              <dl className="grid grid-cols-2 gap-5 p-5">
                <div className="col-span-2 space-y-1">
                  <dt className="text-sm text-muted-foreground">
                    Stored balance
                  </dt>
                  <dd className="break-words text-2xl font-semibold tabular-nums">
                    <span className="mr-2 text-sm font-medium text-muted-foreground">
                      {card.currency}
                    </span>
                    {formatAmount(card.balance)}
                  </dd>
                </div>
                <div className="col-span-2 space-y-1 border-t pt-4">
                  <dt className="text-sm text-muted-foreground">
                    Credit limit
                  </dt>
                  <dd className="break-words text-base font-medium tabular-nums">
                    {card.credit_limit !== null && (
                      <span className="mr-2 text-sm text-muted-foreground">
                        {card.currency}
                      </span>
                    )}
                    {formatAmount(card.credit_limit)}
                  </dd>
                </div>
                <div className="space-y-1">
                  <dt className="text-xs text-muted-foreground">Opened</dt>
                  <dd className="text-sm tabular-nums">
                    {card.opened ?? "Not available"}
                  </dd>
                </div>
                <div className="space-y-1">
                  <dt className="text-xs text-muted-foreground">Expires</dt>
                  <dd className="text-sm tabular-nums">
                    {card.expires ?? "Not available"}
                  </dd>
                </div>
              </dl>
            </article>
          ))}
        </div>
      )}
      <p className="text-sm text-muted-foreground">
        Card payments, recharge, blocking and limit changes are unavailable.
      </p>
    </section>
  );
};

export default CreditCardManagement;
