import { isValidElement, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createInstance } from "i18next";
import en from "@/locales/en.json";
import es from "@/locales/es.json";
import pt from "@/locales/pt.json";
import ProductSummaryCard from "./ProductSummaryCard";
import { formatProductAmount } from "@/common/productAmount";
import type { CardSummary } from "@/api/authClient";

const h = vi.hoisted(() => ({ locale: "en", t: (key: string) => key }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: h.t, i18n: { language: h.locale } }) }));
vi.mock("react-router-dom", () => ({ Link: "a" }));

function text(node: ReactNode): string {
  if (Array.isArray(node)) return node.map(text).join(" ");
  if (isValidElement<{ children?: ReactNode }>(node)) return text(node.props.children);
  return typeof node === "string" || typeof node === "number" ? String(node) : "";
}

const product: CardSummary = {
  product_id: "card-id", number: "4111111111111234", type: "Credit Card",
  currency: "USD", balance: "1234.5600", status: "Active", credit_limit: "9000.0000",
  opened: "2020-01-01", expires: "2030-01-01",
};

describe("product summary", () => {
  beforeEach(() => { h.locale = "en"; h.t = (key) => key; });

  it("preserves exact precision without redundant fractional zeros", () => {
    expect(formatProductAmount("9007199254740993123.4567", "en")).toBe("9,007,199,254,740,993,123.4567");
    expect(formatProductAmount("1234.5600", "en")).toBe("1,234.56");
    expect(formatProductAmount("1234.0000", "en")).toBe("1,234.00");
    expect(formatProductAmount("1234.5600", "es")).toBe("1234,56");
    expect(formatProductAmount("1234.5600", "pt")).toBe("1.234,56");
    expect(formatProductAmount("-0.0050", "en")).toBe("-0.005");
    expect(formatProductAmount("-12.3400", "en")).toBe("-12.34");
    expect(formatProductAmount("invalid", "en")).toBe("invalid");
  });

  it.each(["en", "es", "pt"])("localizes summary labels, status and amounts in %s", async (locale) => {
    const i18n = createInstance();
    await i18n.init({ lng: locale, resources: { en: { translation: en }, es: { translation: es }, pt: { translation: pt } } });
    h.locale = locale; h.t = (key) => String(i18n.t(key));
    const rendered = text(ProductSummaryCard({ product, kind: "card", headingId: "summary" }));
    for (const key of ["Credit Card", "Active", "Stored balance", "Credit limit", "Opened", "Expires"]) {
      expect(rendered).toContain(String(i18n.t(key)));
    }
    expect(rendered).toContain(formatProductAmount(product.balance!, locale));
    expect(rendered).toContain("4111 **** **** 1234");
    expect(rendered).not.toContain(product.number);
    expect(rendered).toContain(product.opened);
    expect(rendered).toContain(product.expires);
  });

  it.each([
    ["en", "Active", "Pending"],
    ["es", "Activo", "Pendiente"],
    ["pt", "Ativo", "Pendente"],
  ])("localizes normalized active and pending statuses in %s", async (locale, active, pending) => {
    const i18n = createInstance();
    await i18n.init({ lng: locale, resources: { en: { translation: en }, es: { translation: es }, pt: { translation: pt } } });
    h.locale = locale; h.t = (key) => String(i18n.t(key));
    for (const [status, expected] of [["active", active], [" pending ", pending]]) {
      const rendered = text(ProductSummaryCard({ product: { ...product, status }, kind: "card", headingId: "summary" }));
      expect(rendered).toContain(expected);
    }
  });

  it("keeps the bank number visible and omits card-only fields for accounts", () => {
    const rendered = text(ProductSummaryCard({ product: { ...product, type: "Savings Account" }, kind: "account", headingId: "summary" }));
    expect(rendered).toContain(product.number);
    expect(rendered).not.toContain("Credit limit");
    expect(rendered).not.toContain("Expires");
  });

  it("does not expose a credit limit on debit cards", () => {
    const rendered = text(ProductSummaryCard({ product: { ...product, type: "Debit Card" }, kind: "card", headingId: "summary" }));
    expect(rendered).toContain("4111 **** **** 1234");
    expect(rendered).not.toContain("Credit limit");
    expect(rendered).not.toContain("9,000.00");
  });

  it("renders unavailable values without fabricating financial data", () => {
    const rendered = text(ProductSummaryCard({ product: { ...product, balance: null, credit_limit: null, opened: null, expires: null }, kind: "card", headingId: "summary" }));
    expect(rendered.match(/Not available/g)).toHaveLength(4);
    expect(rendered).not.toContain("0.00");
  });
});
