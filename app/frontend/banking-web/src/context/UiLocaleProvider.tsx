import { useEffect, useMemo, type ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { useAuth } from "./AuthContext";
import { createUiI18n, resolveUiLocale } from "../i18n";

export function UiLocaleProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const locale = resolveUiLocale(user?.locale);
  const instance = useMemo(() => createUiI18n(locale), [locale]);
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  return <I18nextProvider i18n={instance}>{children}</I18nextProvider>;
}
