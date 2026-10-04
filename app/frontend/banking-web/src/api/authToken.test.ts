import { describe, expect, it } from "vitest";
import { getTokenExpiry } from "./authToken";

const token = (payload: unknown) => `header.${btoa(JSON.stringify(payload)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")}.signature`;

describe("UI expiry scheduling", () => {
  it("decodes base64url expiry without using payload identity claims", () => {
    expect(getTokenExpiry(token({ exp: 2_000_000_000, role: "admin", customer_id: "untrusted" }))).toBe(2_000_000_000_000);
  });
  it.each([{}, { exp: "2000000000" }, { exp: null }, { exp: 0 }, { exp: -1 }, { exp: 1e308 }])("rejects unusable expiry %j", (payload) => {
    expect(getTokenExpiry(token(payload))).toBeNull();
  });
  it.each(["", "opaque-token", "header.invalid!.signature", "header.bnVsbA.signature"])("rejects malformed token %s", (value) => {
    expect(getTokenExpiry(value)).toBeNull();
  });
});
