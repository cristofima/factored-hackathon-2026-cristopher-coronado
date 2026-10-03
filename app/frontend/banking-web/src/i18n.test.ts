import { describe, expect, it } from "vitest";
import { createUiI18n, english, resolveUiLocale, translations } from "./i18n";
import { supportCaseEventMessageKey } from "./models/SupportCase";

describe("profile UI locale", () => {
    it.each(["en", "es", "pt"])("localizes dispute messages and recommendations in %s", (locale) => {
        const instance = createUiI18n(locale);
        const catalog = (locale === "en" ? english : translations[locale as "es" | "pt"])["support-cases"];
        expect(Object.keys(catalog.messages).sort()).toEqual(Object.keys(english["support-cases"].messages).sort());
        expect(Object.keys(catalog.recommendations)).toEqual(Object.keys(english["support-cases"].recommendations));
        for (const eventType of Object.keys(english["support-cases"].events)) {
            const key = supportCaseEventMessageKey({ eventType, message: "stored audit text", actor: "system", createdAt: "" });
            const message = instance.t(key, { keySeparator: ".", transactionId: "TX-DEMO" });
            expect(message).not.toBe(key);
            expect(message).not.toContain("{{");
            if (eventType === "CASE_OPENED") expect(message).toContain("TX-DEMO");
        }
        for (const [message, suffix] of [
            ["Provisional credit issued; case resolved without manual review", "PROVISIONAL_CREDIT"],
            ["Case closed: withdrawn by customer", "WITHDRAWN"],
            ["No fraud score available for this transaction; routed to manual review (no agent available)", "INSUFFICIENT_SIGNAL"],
        ]) {
            const key = supportCaseEventMessageKey({ eventType: suffix === "INSUFFICIENT_SIGNAL" ? "ESCALATED_TO_REVIEW" : "RESOLVED", message, actor: "system", createdAt: "" });
            expect(key).toBe(`support-cases.messages.${suffix}`);
            expect(instance.t(key, { keySeparator: "." })).toBe(catalog.messages[suffix as keyof typeof catalog.messages]);
        }
        expect(instance.t("support-cases.recommendations.transaction_alerts", { keySeparator: "." })).toBe(catalog.recommendations.transaction_alerts);
    });
    it.each([["es", "Resumen"], ["pt", "Resumo"], ["en", "Dashboard"], ["fr", "Dashboard"], [undefined, "Dashboard"]])(
        "selects %s without browser detection", (locale, label) => {
            expect(createUiI18n(locale).t("Dashboard")).toBe(label);
        },
    );
    it("keeps separate users and resets to English without a profile", () => {
        const spanish = createUiI18n("es");
        const portuguese = createUiI18n("pt");
        expect(spanish.t("Account")).toBe("Cuenta");
        expect(portuguese.t("Account")).toBe("Conta");
        expect(createUiI18n(null).t("Account")).toBe("Account");
        expect(resolveUiLocale("es-MX")).toBe("en");
    });
    it("has matching catalogs and preserves interpolation", () => {
        expect(Object.keys(translations.pt).sort()).toEqual(Object.keys(translations.es).sort());
        expect(Object.keys(english).sort()).toEqual(Object.keys(translations.es).sort());
        expect(createUiI18n("es").t("Customer {{id}}", { id: "demo" })).toBe("Cliente demo");
    });
    it.each([
        ["en", ["Health", "Other", "Food", "Services", "Entertainment", "Transport"]],
        ["es", ["Salud", "Otros", "Alimentación", "Servicios", "Entretenimiento", "Transporte"]],
        ["pt", ["Saúde", "Outros", "Alimentação", "Serviços", "Entretenimento", "Transporte"]],
    ])("localizes transaction categories in %s", (locale, expected) => {
        const instance = createUiI18n(locale);
        const values = Object.keys(english.transactions.categories);
        expect(Object.keys(translations.es.transactions.categories)).toEqual(values);
        expect(Object.keys(translations.pt.transactions.categories)).toEqual(values);
        expect(values.map(value => instance.t(`transactions.categories.${value}`, {
            keySeparator: ".", defaultValue: value,
        }))).toEqual(expected);
        expect(instance.t("transactions.categories.Unknown", {
            keySeparator: ".", defaultValue: "Unknown",
        })).toBe("Unknown");
    });
    it.each([
        ["en", ["Payment", "Adjustment", "Transfer", "Purchase", "Withdrawal", "Deposit"], ["Approved", "Reversed", "Declined", "Pending"]],
        ["es", ["Pago", "Ajuste", "Transferencia", "Compra", "Retiro", "Depósito"], ["Aprobada", "Revertida", "Rechazada", "Pendiente"]],
        ["pt", ["Pagamento", "Ajuste", "Transferência", "Compra", "Saque", "Depósito"], ["Aprovada", "Revertida", "Recusada", "Pendente"]],
    ])("localizes transaction labels in %s without changing canonical values", (locale, types, statuses) => {
        const instance = createUiI18n(locale);
        for (const [group, expected] of [["types", types], ["statuses", statuses]] as const) {
            const values = Object.keys(english.transactions[group]);
            expect(Object.keys(translations.es.transactions[group])).toEqual(values);
            expect(Object.keys(translations.pt.transactions[group])).toEqual(values);
            expect(values.map(value => instance.t(`transactions.${group}.${value}`, {
                keySeparator: ".", defaultValue: value,
            }))).toEqual(expected);
        }
        expect(instance.t("transactions.types.Unknown", {
            keySeparator: ".", defaultValue: "Unknown",
        })).toBe("Unknown");
        expect(instance.t("Customer {{id}}", { id: "demo" })).not.toContain("{{id}}");
    });
});