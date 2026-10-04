import type { AccountSummary, CardSummary } from "@/api/authClient";

export function productPath(productId: string): string {
  return `/product/${encodeURIComponent(productId)}`;
}

export function resolveProduct(accounts: AccountSummary[], cards: CardSummary[], productId: string | undefined) {
  if (!productId) return undefined;
  const matches = [
    ...accounts.filter((item) => item.product_id === productId).map((item) => ({ item, kind: "account" as const })),
    ...cards.filter((item) => item.product_id === productId).map((item) => ({ item, kind: "card" as const })),
  ];
  if (matches.length !== 1) return undefined;
  const match = matches[0];
  if (match.kind === "account" && (!match.item.number?.trim() || accounts.filter((item) => item.number === match.item.number).length !== 1)) return undefined;
  return match;
}

export function maskedCardNumber(number: string | null): string | null {
  const compact = number?.replace(/[\s-]/g, "") ?? "";
  if (/^\d{4}\*+\d{4}$/.test(compact)) {
    return `${compact.slice(0, 4)} **** **** ${compact.slice(-4)}`;
  }
  if (/^\*+\d{4}$/.test(compact)) return `**** ${compact.slice(-4)}`;
  if (!/^\d{12,19}$/.test(compact)) return null;
  return `${compact.slice(0, 4)} **** **** ${compact.slice(-4)}`;
}

export function productStatusKey(status: string | null): string {
  const labels: Record<string, string> = {
    active: "Active", inactive: "Inactive", blocked: "Blocked", closed: "Closed",
    expired: "Expired", suspended: "Suspended", pending: "Pending",
  };
  return labels[status?.trim().toLowerCase() ?? ""] ?? "Status unavailable";
}
