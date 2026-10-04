import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useProductCatalog } from "@/hooks/useProductCatalog";
import { maskedCardNumber, productPath, resolveProduct } from "@/common/products";
import { Button } from "@/components/ui/button";

export default function Dashboard() {
  const { t } = useTranslation();
  const { accounts, cards, loading, error, retry } = useProductCatalog();
  const [category, setCategory] = useState("All");
  const products = [
    ...accounts.map((item) => ({ item, category: "Accounts", number: item.number })),
    ...cards.map((item) => ({ item, category: "Cards", number: maskedCardNumber(item.number) })),
  ];
  const visible = products.filter((product) => category === "All" || product.category === category);
  return (
    <section className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">{t("My products")}</h1>
      <fieldset className="flex flex-wrap gap-2">
        <legend className="mb-3 text-sm font-medium">{t("Product category")}</legend>
        {["All", "Accounts", "Cards"].map((value) => (
          <Button key={value} variant={category === value ? "default" : "outline"} aria-pressed={category === value} onClick={() => setCategory(value)}>{t(value)}</Button>
        ))}
      </fieldset>
      {loading && <output>{t("Loading products...")}</output>}
      {error && <div role="alert"><p>{t(error)}</p><Button variant="outline" onClick={retry}>{t("Retry")}</Button></div>}
      {!loading && !error && !visible.length && <output>{t("No products in this category.")}</output>}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {visible.map(({ item, number, category: kind }, index) => {
          const content = <><span className="block font-semibold">{t(item.type)}</span><span className="block break-all font-mono">{number ?? t("Number unavailable")}</span><span className="block text-sm text-muted-foreground">{item.currency} · {t(item.status ?? "Status unavailable")}</span><span className="block mt-3 text-lg font-semibold tabular-nums">{t("Stored balance")}: {item.balance === null ? t("Not available") : `${item.currency} ${item.balance}`}</span></>;
          const className = "min-w-0 rounded-lg border bg-card p-5 text-left shadow-sm";
          return resolveProduct(accounts, cards, item.product_id)
            ? <Link key={`${kind}:${item.product_id}`} to={productPath(item.product_id)} className={`${className} hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring`}>{content}<span className="block mt-3 text-sm text-primary">{t("View product movements")}</span></Link>
            : <div key={`${kind}:${index}`} className={className}>{content}<span className="block mt-3 text-sm text-muted-foreground">{t("Selected product is unavailable.")}</span></div>;
        })}
      </div>
    </section>
  );
}
