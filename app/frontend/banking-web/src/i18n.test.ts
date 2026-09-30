import { describe, expect, it } from "vitest";
import { createUiI18n, english, resolveUiLocale, translations } from "./i18n";

describe("profile UI locale", () => {
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