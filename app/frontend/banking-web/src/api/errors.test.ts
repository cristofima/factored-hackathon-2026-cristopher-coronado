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
        { detail: "Private English backend failure" },
        { detail: { code: "UNKNOWN_PRIVATE_ERROR" } },
        { detail: [{ msg: "Validation failed" }] },
        null,
    ])("does not expose uncontrolled response details", async body => {
        const error = await readApiError(Response.json(body, { status: 500 }));
        expect(error.code).toBe("SERVICE_UNAVAILABLE");
        expect(errorTranslationKey(error, "Request failed")).toBe("Request failed");
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