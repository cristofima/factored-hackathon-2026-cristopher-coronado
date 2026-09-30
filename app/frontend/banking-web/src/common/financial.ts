import type { FinancialTransaction } from "../api/financialClient";

// Fixed-scale integers preserve Numeric(20,4) amounts without float rounding.
export function decimalUnits(value: string): bigint {
    if (!/^-?\d+(\.\d{1,4})?$/.test(value)) throw new Error("Invalid financial amount");
    const negative = value.startsWith("-");
    const [whole, fraction = ""] = value.replace(/^-/, "").split(".");
    const units = BigInt(whole) * BigInt(10000) + BigInt(fraction.padEnd(4, "0"));
    return negative ? -units : units;
}

export function decimalString(units: bigint): string {
    const absolute = units < BigInt(0) ? -units : units;
    return `${units < BigInt(0) ? "-" : ""}${absolute / BigInt(10000)}.${String(absolute % BigInt(10000)).padStart(4, "0")}`;
}

export function calendarDate(value: Date): string {
    return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

export function summarizeTransactions(records: FinancialTransaction[]) {
    const currencies = new Map<string, { inflow: bigint; outflow: bigint; count: number }>();
    let excluded = 0;
    for (const record of records) {
        const amount = decimalUnits(record.amount);
        const direction = record.type === "Deposit" ? "inflow"
            : ["Payment", "Purchase", "Transfer", "Withdrawal"].includes(record.type ?? "") ? "outflow" : null;
        if (record.status !== "Approved" || direction === null || amount < BigInt(0)) {
            excluded += 1;
            continue;
        }
        const group = currencies.get(record.currency) ?? { inflow: BigInt(0), outflow: BigInt(0), count: 0 };
        group[direction] += amount;
        group.count += 1;
        currencies.set(record.currency, group);
    }
    return { currencies, excluded };
}