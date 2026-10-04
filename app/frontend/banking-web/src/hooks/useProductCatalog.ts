import { useEffect, useState } from "react";
import { getAccounts, getCards, type AccountSummary, type CardSummary } from "@/api/authClient";
import { errorTranslationKey } from "@/api/errors";
import { useAuth } from "@/context/AuthContext";

export function useProductCatalog() {
  const { user, sessionKey } = useAuth();
  const scope = JSON.stringify([user?.id, sessionKey]);
  const [accounts, setAccounts] = useState<AccountSummary[]>([]);
  const [cards, setCards] = useState<CardSummary[]>([]);
  const [catalogScope, setCatalogScope] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setAccounts([]);
    setCards([]);
    setCatalogScope("");
    setLoading(true);
    setError(null);
    Promise.all([getAccounts(controller.signal), getCards(controller.signal)])
      .then(([accountItems, cardItems]) => {
        if (!controller.signal.aborted) {
          setAccounts(accountItems);
          setCards(cardItems);
          setCatalogScope(scope);
        }
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setCatalogScope(scope);
          setError(errorTranslationKey(cause, "Products are unavailable"));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [scope, attempt]);

  const current = catalogScope === scope;
  return {
    accounts: current ? accounts : [], cards: current ? cards : [], scope,
    loading: !current || loading, error: current ? error : null,
    retry: () => setAttempt((value) => value + 1),
  };
}
