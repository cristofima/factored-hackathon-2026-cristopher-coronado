import { useTranslation } from "react-i18next";

export default function InvestmentPortfolio() {
  const { t } = useTranslation();
  return (
    <section className="p-6 space-y-4">
      <h1 className="text-2xl font-bold">{t("Investment Portfolio")}</h1>
      <p role="status">{t("Investments unavailable")}</p>
    </section>
  );
}
