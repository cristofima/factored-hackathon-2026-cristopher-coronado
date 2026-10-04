import { useCallback, useEffect, useState } from "react";
import { listSupportCases } from "@/api/disputeClient";
import { useAuth } from "@/context/AuthContext";
import type { SupportCase } from "@/models/SupportCase";

export function activeTransactionCases(cases: SupportCase[]): Map<string, SupportCase> {
  return new Map(cases.filter((item) => item.status !== "RESOLVED")
    .map((item) => [item.transactionId, item]));
}

export function useDisputeEligibility(enabled: boolean) {
  const { user, sessionKey } = useAuth();
  const customerId = user?.id;
  const scope = JSON.stringify([customerId, sessionKey]);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{
    scope: string; attempt: number; cases: SupportCase[]; status: "ready" | "error";
  } | null>(null);
  const refresh = useCallback(() => setAttempt((value) => value + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    setState(null);
    if (enabled && customerId) {
      void listSupportCases(controller.signal).then((cases) => {
        if (!controller.signal.aborted) setState({ scope, attempt, cases, status: "ready" });
      }).catch(() => {
        if (!controller.signal.aborted) setState({ scope, attempt, cases: [], status: "error" });
      });
    }
    return () => controller.abort();
  }, [enabled, scope, attempt, customerId]);

  const current = enabled && customerId && state?.scope === scope && state.attempt === attempt ? state : null;
  return {
    scope,
    status: current?.status ?? "loading",
    activeCases: activeTransactionCases(current?.cases ?? []),
    refresh,
  };
}
