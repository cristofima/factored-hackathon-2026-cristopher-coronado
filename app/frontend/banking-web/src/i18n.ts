import english from "./locales/en.json";
import spanish from "./locales/es.json";
import portuguese from "./locales/pt.json";
import { createInstance } from "i18next";
import { initReactI18next } from "react-i18next";

export const resolveUiLocale = (value: unknown): "en" | "es" | "pt" =>
    value === "es" || value === "pt" ? value : "en";

export { english };
export const translations = { es: spanish, pt: portuguese };

export const createUiI18n = (locale: unknown) => {
    const instance = createInstance();
    void instance.use(initReactI18next).init({
        lng: resolveUiLocale(locale), fallbackLng: "en", supportedLngs: ["en", "es", "pt"],
        resources: { en: { translation: english }, es: { translation: translations.es }, pt: { translation: translations.pt } },
        keySeparator: false, nsSeparator: false, initImmediate: false,
        interpolation: { escapeValue: false }, react: { useSuspense: false },
    });
    return instance;
};