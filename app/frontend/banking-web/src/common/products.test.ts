import { describe, expect, it } from "vitest";
import { maskedCardNumber, productStatusKey } from "./products";

describe("card number display", () => {
  it.each([
    ["4111111111111234", "4111 **** **** 1234"],
    ["4111-1111 1111-1234", "4111 **** **** 1234"],
    ["4111 **** **** 1234", "4111 **** **** 1234"],
    ["**** 1234", "**** 1234"],
    [null, null], ["", null], ["41111234", null],
    ["4111text1234", null], ["４１１１１１１１１１１１１２３４", null],
    ["41111111111111111234", null],
  ])("safely projects %s", (input, expected) => {
    expect(maskedCardNumber(input)).toBe(expected);
  });
});

describe("product status labels", () => {
  it.each(["active", "Active", " ACTIVE "])("normalizes %s without changing stored values", (status) => {
    expect(productStatusKey(status)).toBe("Active");
  });
  it.each([null, "unknown"])("uses an unavailable label for %s", (status) => {
    expect(productStatusKey(status)).toBe("Status unavailable");
  });
});
