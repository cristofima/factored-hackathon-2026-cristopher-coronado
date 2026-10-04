import { resolveUiLocale } from "@/i18n";

export type DateTimeDisplayFormat = "YYYY-MM-DD" | "date-time" | "date-time-seconds";

export function formatDateTime(value: string, locale: unknown, format: DateTimeDisplayFormat = "date-time"): string {
  // Date-only financial displays preserve the source calendar date without timezone conversion.
  if (format === "YYYY-MM-DD") return value.slice(0, 10);

  const includeSeconds = format === "date-time-seconds";
  const parts = new Intl.DateTimeFormat(resolveUiLocale(locale), {
    day: "numeric", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", ...(includeSeconds ? { second: "2-digit" as const } : {}),
    hourCycle: "h23",
  }).formatToParts(new Date(value));
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find(item => item.type === type)?.value;
  return `${part("day")} ${part("month")} ${part("year")}, ${part("hour")}:${part("minute")}${includeSeconds ? `:${part("second")}` : ""}`;
}
