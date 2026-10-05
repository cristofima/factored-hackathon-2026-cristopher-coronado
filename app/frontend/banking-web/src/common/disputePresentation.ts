import type { TFunction } from "i18next";
import { productStatusKey } from "./products";
import { formatProductAmount } from "./productAmount";

export function formatStoredScore(value: string, locale: string): string {
  if (!/^-?\d+(\.\d{1,4})?$/.test(value)) return value;
  const formatted = formatProductAmount(value, locale);
  const separator = new Intl.NumberFormat(locale).formatToParts(1.1).find(part => part.type === "decimal")?.value ?? ".";
  return formatted.endsWith(`${separator}00`) ? formatted.slice(0, -3) : formatted;
}

const productTypes = ["Savings Account", "Checking Account", "Debit Card", "Credit Card"];

export function disputeProductLabel(value: string, t: TFunction): string {
  return productTypes.includes(value) ? t(value) : t("Unavailable");
}

export function disputeTransactionStatus(value: string, t: TFunction): string {
  return ["Approved", "Declined", "Pending", "Reversed"].includes(value)
    ? t(`transactions.statuses.${value}`, { keySeparator: ".", defaultValue: t("Unavailable") }) : t("Unavailable");
}

export function disputeProtectionStatus(value: string | null | undefined, t: TFunction): string {
  return value == null ? t("Unavailable") : t(productStatusKey(value));
}

export function disputeSourceLabel(value: string, t: TFunction): string {
  return ["source", "dispute_effect"].includes(value)
    ? t(`operator.sources.${value}`, { keySeparator: ".", defaultValue: t("Unavailable") }) : t("Unavailable");
}
