import { describe, expect, it } from "vitest";
import { ApiError, errorTranslationKey, readApiError } from "./errors";
import { createUiI18n } from "../i18n";

describe("controlled API errors", () => {
    it.each(["AUTH_REQUIRED", "ACCESS_DENIED", "INVALID_DATE_RANGE", "ACCOUNT_UNAVAILABLE"])(
        "accepts the controlled code %s", async code => {
            const error = await readApiError(Response.json({ detail: { code } }, { status: 422 }));
            expect(error.code).toBe(code);
        },
    );

    it.each([
        ["DISPUTE_PREVIEW_INVALID", "Dispute preview unavailable", 400],
        ["DISPUTE_PREVIEW_EXPIRED", "Dispute preview expired", 400],
        ["DISPUTE_PREVIEW_STALE", "Dispute preview unavailable", 409],
        ["DISPUTE_UNAVAILABLE", "Dispute preview unavailable", 403],
        ["DISPUTE_INELIGIBLE", "Dispute preview unavailable", 400],
    ] as const)("preserves and localizes %s", async (code, key, status) => {
        const error = await readApiError(Response.json({ detail: { code } }, { status }));
        expect(error.code).toBe(code);
        expect(errorTranslationKey(error, "Request failed")).toBe(key);
        for (const locale of ["en", "es", "pt"]) {
            const message = createUiI18n(locale).t(key);
            expect(message).not.toBe(code);
            if (locale !== "en") expect(message).not.toBe(key);
        }
    });

    it.each([
        { detail: "Private English backend failure" },
        { detail: { code: "UNKNOWN_PRIVATE_ERROR" } },
        { detail: [{ msg: "Validation failed" }] },
        null,
    ])("does not expose uncontrolled response details", async body => {
        const error = await readApiError(Response.json(body, { status: 500 }));
        expect(error.code).toBe("SERVICE_UNAVAILABLE");
        expect(errorTranslationKey(error, "Request failed")).toBe("Request failed");
    });

    it("preserves and localizes the controlled active-dispute conflict", async () => {
        const error = await readApiError(Response.json({ detail: { code: "DISPUTE_ALREADY_ACTIVE" } }, { status: 409 }));
        expect(error.code).toBe("DISPUTE_ALREADY_ACTIVE");
        const key = errorTranslationKey(error, "Could not open the dispute");
        expect(key).toBe("An active dispute already exists. Retry to open the existing case.");
        for (const locale of ["es", "pt"]) expect(createUiI18n(locale).t(key)).not.toBe(key);
    });

    it.each([
        ["en", "Only debit or credit card transactions can be disputed."],
        ["es", "Solo se pueden reclamar transacciones de tarjetas de débito o crédito."],
        ["pt", "Somente transações de cartões de débito ou crédito podem ser contestadas."],
    ])("localizes the controlled card-only rejection in %s", async (locale, message) => {
        const error = await readApiError(Response.json({ detail: { code: "DISPUTE_CARD_ONLY" } }, { status: 400 }));
        expect(error.code).toBe("DISPUTE_CARD_ONLY");
        const key = errorTranslationKey(error, "Could not open the dispute");
        expect(createUiI18n(locale).t(key)).toBe(message);
    });

    it("handles non-JSON and legacy authentication errors", async () => {
        const error = await readApiError(new Response("Not JSON", { status: 401 }));
        expect(error.code).toBe("AUTH_REQUIRED");
    });

    it.each(["es", "pt"])("localizes known and unknown failures in %s", locale => {
        const i18n = createUiI18n(locale);
        const known = errorTranslationKey(new ApiError("AUTH_REQUIRED"), "Request failed");
        const unknown = errorTranslationKey(new Error("Private English failure"), "Request failed");
        expect(i18n.t(known)).not.toBe("Session expired");
        expect(i18n.t(unknown)).not.toBe("Request failed");
    });
});