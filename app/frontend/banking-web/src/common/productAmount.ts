export function formatProductAmount(value: string, locale: string): string {
  if (!/^-?\d+(\.\d{1,4})?$/.test(value)) return value;
  const [whole, fraction = ""] = value.split(".");
  const digits = fraction.replace(/0+$/, "").padEnd(2, "0");
  const separator = new Intl.NumberFormat(locale).formatToParts(1.1).find((part) => part.type === "decimal")?.value ?? ".";
  const grouped = new Intl.NumberFormat(locale).format(BigInt(whole));
  return `${whole.startsWith("-") && BigInt(whole) === BigInt(0) ? "-" : ""}${grouped}${separator}${digits}`;
}
